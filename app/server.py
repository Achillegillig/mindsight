"""Routes HTTP et coordination des deux traitements d’un tour."""

import json
import logging
import os
from collections import deque
from concurrent.futures import Future, ThreadPoolExecutor
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler
from threading import Lock
from uuid import uuid4

from .azure_speech import SpeechError
from .dialogue import (
    CLOSING, FOLLOWUP_STEPS, OPENING, QUESTIONS, PromptError, next_step,
    read_followup_prompt, validate_messages,
)
from .extraction import ExtractionError, extract_turn, observe_turn
from .openrouter import OpenRouterError, generate_reply
from .prompt_config import DIRECTORY
from .quantification import quantify_dimensions, scores_on_ten

STATIC = {
    "/": ("index.html", "text/html"),
    "/static/chat.css": ("chat.css", "text/css"),
    "/static/chat.js": ("chat.js", "text/javascript"),
    "/static/voice.js": ("voice.js", "text/javascript"),
}
TURN_PATH = "/api/conversation/turn"
SESSION_PATH = "/api/conversation/session"
SPEECH_PATH = "/api/speech"
MAX_BODY_BYTES = 256 * 1024
RECORD_PATH = DIRECTORY.parent / "test-results.jsonl"
RECORD_LOCK = Lock()
LOGGER = logging.getLogger(__name__)


def record_turn(path, messages, result):
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "turn": len(messages) // 2,
        "question": messages[-2]["content"],
        "answer": messages[-1]["content"],
        **result,
    }
    line = json.dumps(entry, ensure_ascii=False) + "\n"
    with RECORD_LOCK, open(path, "a", encoding="utf-8", opener=open_private) as output:
        output.write(line)


def open_private(filename, flags):
    return os.open(filename, flags, 0o600)


def analysis_status(extraction):
    if extraction is None:
        return "failed"
    return "ready" if extraction["dimensions"] is not None else "partial"


class TurnConflict(ValueError):
    pass


@dataclass
class Session:
    history: list = field(default_factory=lambda: [OPENING.copy()])
    requests: dict = field(default_factory=dict)
    episodes: dict = field(default_factory=dict)
    indices: list = field(default_factory=list)
    queue: deque = field(default_factory=deque)
    dialogue_lock: Lock = field(default_factory=Lock)
    state_lock: Lock = field(default_factory=Lock)
    draining: bool = False
    analysis_job: Future | None = None
    finished_turn: int | None = None
    snapshot: dict = field(default_factory=dict)
    reasoning_turns: list = field(default_factory=list)


class ConversationService:
    def __init__(self, catalog, *, model=None, api_key=None, record_path=None, reasoning=False,
                 extractor=extract_turn, observer=observe_turn, dialogue=generate_reply):
        self.catalog = catalog
        self.model = model
        self.api_key = api_key
        self.record_path = record_path
        self.reasoning = reasoning
        self.extractor = extractor
        self.observer = observer
        self.dialogue = dialogue
        self.executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="mindsight")
        self.sessions = {}
        self.sessions_lock = Lock()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.executor.shutdown()

    def create_session(self):
        session_id = uuid4().hex
        session = Session(snapshot={
            "session_id": session_id, "catalog_version": self.catalog.version,
            "revision": 0, "through_turn": 0, "latest_turn": 0, "analysis_status": "idle",
            "dimensions": quantify_dimensions([], self.catalog), "observations": {},
        })
        with self.sessions_lock:
            self.sessions[session_id] = session
        return session_id

    def get_session(self, session_id):
        with self.sessions_lock:
            return self.sessions[session_id]

    def get_snapshot(self, session_id):
        session = self.get_session(session_id)
        with session.state_lock:
            return deepcopy(session.snapshot)

    def get_scores(self, session_id):
        session = self.get_session(session_id)
        with session.state_lock:
            snapshot = session.snapshot
            ready = session.finished_turn is not None and snapshot["through_turn"] >= session.finished_turn
            return {
                "session_id": session_id,
                "catalog_version": snapshot["catalog_version"],
                "through_turn": snapshot["through_turn"],
                "analysis_status": snapshot["analysis_status"],
                "ready": ready,
                "traits": scores_on_ten(snapshot["dimensions"]) if ready else [],
            }

    def get_reasoning(self, session_id):
        session = self.get_session(session_id)
        with session.state_lock:
            return deepcopy({
                **{key: session.snapshot[key] for key in ("analysis_status", "through_turn", "latest_turn")},
                "dimensions": quantify_dimensions(session.indices, self.catalog, include_calculation=True),
                "turns": session.reasoning_turns,
            })

    def observe(self, messages):
        try:
            return self.observer(
                self.api_key, self.model, messages[-2]["content"], messages[-1]["content"],
                include_trace=self.reasoning,
            )
        except ExtractionError:
            LOGGER.warning("Observations indisponibles pour un tour.")
        except Exception:
            LOGGER.error("Erreur interne durant l’observation d’un tour.")
        return None

    def analyze(self, messages, known_episodes=(), *, observed=None):
        try:
            return self.extractor(
                self.api_key, self.model, messages[-2]["content"], messages[-1]["content"],
                catalog=self.catalog, known_episodes=known_episodes, include_trace=self.reasoning,
                observed=observed,
            )
        except ExtractionError:
            LOGGER.warning("Extraction indisponible pour un tour.")
        except Exception:
            LOGGER.error("Erreur interne durant l’analyse d’un tour.")
        return None

    def reply(self, messages, extraction):
        has_evidence = bool(extraction and (extraction.get("expressed_feelings") or extraction.get("dimensions")))
        step, reply = next_step(messages, has_evidence=has_evidence)
        if step in FOLLOWUP_STEPS and self.model and extraction is not None:
            prompt = read_followup_prompt(step)
            # The second follow-up also sees the first exchange of this question.
            context = messages[-4:] if step == "experience" else messages[-2:]
            try:
                generated = self.dialogue(self.api_key, self.model, prompt, context)
                previous_questions = {item["content"] for item in messages[::2]}
                if (generated not in previous_questions and generated not in QUESTIONS
                        and generated.endswith("?") and generated.count("?") == 1
                        and len(generated) <= 220):
                    reply = generated
            except OpenRouterError:
                LOGGER.warning("Relance indisponible. Une question préparée est utilisée.")
        return reply, step == "done"

    def record(self, messages, result, *, snapshot=None):
        if self.record_path is None:
            return
        entry = dict(result)
        if snapshot is not None:
            entry["session_id"] = snapshot["session_id"]
            entry["quantification"] = {
                "scope": "session",
                **{key: snapshot[key] for key in ("catalog_version", "revision", "through_turn", "dimensions")},
            }
        else:
            turn = len(messages) // 2
            extraction = result["extraction"]
            links = (extraction or {}).get("dimensions") or []
            indices = self.collect_indices({}, turn, links)
            entry["analysis_status"] = analysis_status(extraction) if self.model else "simulated"
            entry["quantification"] = {
                "scope": "turn",
                "catalog_version": self.catalog.version,
                "through_turn": turn,
                "dimensions": quantify_dimensions(indices, self.catalog),
            }
        try:
            record_turn(self.record_path, messages, entry)
        except OSError as error:
            LOGGER.error("Écriture du journal de test impossible : %s", error)

    def process_legacy_turn(self, messages):
        if messages[-2]["content"] == CLOSING:
            raise TurnConflict("Cette conversation est terminée.")
        extraction = self.analyze(messages) if self.model else None
        reply, done = self.reply(messages, extraction)
        result = {"reply": reply, "extraction": extraction, "done": done}
        self.record(messages, result)
        return result

    def process_session_turn(self, session_id, request_id, messages):
        session = self.get_session(session_id)
        with session.dialogue_lock:
            previous = session.requests.get(request_id)
            if previous is not None:
                original, result = previous
                if messages != original:
                    raise TurnConflict("Cet identifiant d’envoi correspond déjà à un autre tour.")
                return result
            if messages[:-1] != session.history:
                raise TurnConflict("L’historique ne correspond plus à cette session.")

            if session.history[-1]["content"] == CLOSING:
                raise TurnConflict("Cette conversation est terminée.")

            observations = self.observe(messages) if self.model else None
            extraction = observations
            interpret_later = observations is not None
            if observations and observations["observations"]:
                step, _ = next_step(messages, has_evidence=bool(observations["expressed_feelings"]))
                if step in FOLLOWUP_STEPS:
                    # Earlier turns must finish before we pass their episodes to the model.
                    if session.analysis_job is not None:
                        session.analysis_job.result()
                    extraction = self.analyze(messages, self.known_episodes(session), observed=observations)
                    interpret_later = False
            reply, done = self.reply(messages, extraction)
            session.history = [*messages, {"role": "assistant", "content": reply}]
            turn = len(messages) // 2
            status = "pending" if self.model else "simulated"
            result = {"reply": reply, "extraction": None, "analysis_status": status, "done": done}
            with session.state_lock:
                if done:
                    session.finished_turn = turn
                session.snapshot.update(latest_turn=turn, analysis_status=status)
                if self.model:
                    session.queue.append((turn, messages, reply, done, extraction, interpret_later))
                    if not session.draining:
                        session.draining = True
                        session.analysis_job = self.executor.submit(self.drain_session, session)
                else:
                    session.snapshot.update(through_turn=turn, revision=session.snapshot["revision"] + 1)
                    snapshot = session.snapshot.copy()
            session.requests[request_id] = (messages, result)
            if not self.model:
                self.record(messages, result, snapshot=snapshot)
            return result

    @staticmethod
    def known_episodes(session):
        with session.state_lock:
            return [
                {"id": key, "label": label}
                for key, label in list(session.episodes.items())[-20:]
            ]

    def drain_session(self, session):
        while True:
            with session.state_lock:
                if not session.queue:
                    session.draining = False
                    return
                turn, messages, reply, done, extraction, interpret_later = session.queue.popleft()
            if interpret_later:
                extraction = self.analyze(messages, self.known_episodes(session), observed=extraction)
            links = extraction["dimensions"] if extraction is not None else None
            status = analysis_status(extraction)
            with session.state_lock:
                if extraction is not None:
                    session.snapshot["observations"].update({
                        f"t{turn}:{item['id']}": item for item in extraction["observations"]
                    })
                indices = self.collect_indices(session.episodes, turn, links or [])
                session.indices.extend(indices)
                if self.reasoning:
                    session.reasoning_turns.append({
                        "turn": turn, "status": status, "extraction": extraction,
                        "episode_ids": [index["episode_id"] for index in indices],
                    })
                session.snapshot.update(
                    revision=session.snapshot["revision"] + 1,
                    through_turn=turn,
                    analysis_status="pending" if session.queue else status,
                    dimensions=quantify_dimensions(session.indices, self.catalog),
                )
                snapshot = session.snapshot.copy()
            self.record(messages, {
                "reply": reply, "extraction": extraction, "analysis_status": status, "done": done,
            }, snapshot=snapshot)

    @staticmethod
    def collect_indices(episodes, turn, links):
        indices = []
        for link in links:
            if link.get("relation", "appui") != "appui":
                continue
            episode = link["episode_ref"]
            if episode.startswith("new:"):
                episode = f"t{turn}-{episode[4:]}"
                episodes.setdefault(episode, link["episode_label"] or f"Épisode du tour {turn}")
            elif episode not in episodes:
                episode = "unknown"
            indices.append({
                "dimension_id": link["dimension_id"],
                "strength": link["strength"], "episode_id": episode,
                "source_refs": [f"t{turn}:{item}" for item in link["observation_ids"]],
            })
        return indices


class ConversationHandler(BaseHTTPRequestHandler):
    def __init__(self, *args, service, speech=None, on_session_created=None):
        self.service = service
        self.speech = speech
        self.on_session_created = on_session_created
        super().__init__(*args)

    def send_content(self, status, content, media_type):
        self.send_response(status)
        self.send_header("Content-Type", media_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def send_json(self, status, value):
        self.send_content(status, json.dumps(value, ensure_ascii=False).encode(), "application/json; charset=utf-8")

    def do_GET(self):
        if self.path == "/api/conversation/opening":
            self.send_json(200, OPENING)
        elif self.path == "/api/conversation/mode":
            self.send_json(200, {"model": self.service.model, "azureSpeech": self.speech is not None})
        elif self.path.startswith(f"{SESSION_PATH}/") and self.path.endswith("/scores"):
            session_id = self.path.removeprefix(f"{SESSION_PATH}/").removesuffix("/scores")
            try:
                scores = self.service.get_scores(session_id)
            except KeyError:
                self.send_json(404, {"detail": "Session introuvable."})
            else:
                self.send_json(200, scores)
        elif self.service.reasoning and self.path.startswith(f"{SESSION_PATH}/") and self.path.endswith("/reasoning"):
            session_id = self.path.removeprefix(f"{SESSION_PATH}/").removesuffix("/reasoning")
            try:
                reasoning = self.service.get_reasoning(session_id)
            except KeyError:
                self.send_json(404, {"detail": "Session introuvable."})
            else:
                self.send_json(200, reasoning)
        elif self.path in STATIC:
            filename, media_type = STATIC[self.path]
            self.send_content(200, (DIRECTORY / "static" / filename).read_bytes(), f"{media_type}; charset=utf-8")
        else:
            self.send_json(404, {"detail": "Page introuvable."})

    def do_POST(self):
        if self.path == SESSION_PATH:
            session_id = self.service.create_session()
            self.log_message("Session MindSight : %s", session_id)
            if self.on_session_created is not None:
                self.on_session_created(session_id)
            self.send_json(201, {
                "session_id": session_id, "opening": OPENING, "reasoning": self.service.reasoning,
            })
            return
        if self.path not in (TURN_PATH, SPEECH_PATH):
            self.send_json(404, {"detail": "Route introuvable."})
            return
        if self.headers.get_content_type() != "application/json":
            self.send_json(415, {"detail": "Le corps doit être au format JSON."})
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= MAX_BODY_BYTES:
                raise ValueError("Taille de requête invalide.")
            payload = json.loads(self.rfile.read(size))
        except (ValueError, RecursionError):
            self.send_json(400, {"detail": "Requête JSON invalide."})
            return
        if self.path == SPEECH_PATH:
            self.speak(payload)
            return
        try:
            messages = validate_messages(payload)
        except ValueError as error:
            self.send_json(422, {"detail": str(error)})
            return
        try:
            if "session_id" in payload or "request_id" in payload:
                session_id, request_id = payload.get("session_id"), payload.get("request_id")
                if any(not isinstance(value, str) or not 1 <= len(value) <= 100
                       for value in (session_id, request_id)):
                    self.send_json(422, {"detail": "Identifiants de session et d’envoi requis."})
                    return
                result = self.service.process_session_turn(session_id, request_id, messages)
            else:
                result = self.service.process_legacy_turn(messages)
        except KeyError:
            self.send_json(404, {"detail": "Session introuvable. Clique sur Recommencer."})
            return
        except TurnConflict as error:
            self.send_json(409, {"detail": str(error)})
            return
        except PromptError as error:
            self.send_json(500, {"detail": str(error)})
            return
        except OpenRouterError as error:
            self.send_json(502, {"detail": str(error)})
            return
        self.send_json(200, result)

    def speak(self, payload):
        text = payload.get("text") if isinstance(payload, dict) else None
        if not isinstance(text, str) or not 1 <= len(text.strip()) <= 500:
            self.send_json(422, {"detail": "Une question de 1 à 500 caractères est attendue."})
            return
        if self.speech is None:
            self.send_json(503, {"detail": "Azure Speech n’est pas configuré."})
            return
        try:
            audio = self.speech(text.strip())
        except SpeechError as error:
            self.log_error("%s", error)
            self.send_json(502, {"detail": str(error)})
            return
        try:
            self.send_content(200, audio, "audio/mpeg")
        except (BrokenPipeError, ConnectionResetError):
            return
