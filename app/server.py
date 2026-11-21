"""Routes HTTP et coordination des deux traitements d’un tour."""

import json
import logging
import os
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler
from threading import Lock
from uuid import uuid4

from .dialogue import DIRECTORY, OPENING, PromptError, demo_reply, read_system_prompt, validate_messages
from .extraction import ExtractionError, extract_turn
from .openrouter import OpenRouterError, generate_reply
from .quantification import quantify_dimensions

STATIC = {
    "/": ("index.html", "text/html"),
    "/static/chat.css": ("chat.css", "text/css"),
    "/static/chat.js": ("chat.js", "text/javascript"),
}
TURN_PATH = "/api/conversation/turn"
SESSION_PATH = "/api/conversation/session"
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
    snapshot: dict = field(default_factory=dict)
    reasoning_turns: list = field(default_factory=list)


class ConversationService:
    def __init__(self, catalog, *, model=None, api_key=None, record_path=None, reasoning=False,
                 extractor=extract_turn, dialogue=generate_reply):
        self.catalog = catalog
        self.model = model
        self.api_key = api_key
        self.record_path = record_path
        self.reasoning = reasoning
        self.extractor = extractor
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

    def get_reasoning(self, session_id):
        session = self.get_session(session_id)
        with session.state_lock:
            return deepcopy({
                **{key: session.snapshot[key] for key in ("analysis_status", "through_turn", "latest_turn")},
                "dimensions": quantify_dimensions(session.indices, self.catalog, include_calculation=True),
                "turns": session.reasoning_turns,
            })

    def analyze(self, messages, known_episodes=()):
        try:
            return self.extractor(
                self.api_key, self.model, messages[-2]["content"], messages[-1]["content"],
                catalog=self.catalog, known_episodes=known_episodes, include_trace=self.reasoning,
            )
        except ExtractionError:
            LOGGER.warning("Extraction indisponible pour un tour.")
        except Exception:
            LOGGER.error("Erreur interne durant l’analyse d’un tour.")
        return None

    def reply(self, messages):
        if not self.model:
            return demo_reply(messages)
        return self.dialogue(self.api_key, self.model, read_system_prompt(), messages)

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
        job = self.executor.submit(self.analyze, messages) if self.model else None
        result = {"reply": self.reply(messages), "extraction": job.result() if job else None}
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

            reply = self.reply(messages)
            session.history = [*messages, {"role": "assistant", "content": reply}]
            turn = len(messages) // 2
            status = "pending" if self.model else "simulated"
            result = {"reply": reply, "extraction": None, "analysis_status": status}
            with session.state_lock:
                session.snapshot.update(latest_turn=turn, analysis_status=status)
                if self.model:
                    session.queue.append((turn, messages, reply))
                    if not session.draining:
                        session.draining = True
                        self.executor.submit(self.drain_session, session)
                else:
                    session.snapshot.update(through_turn=turn, revision=session.snapshot["revision"] + 1)
                    snapshot = session.snapshot.copy()
            session.requests[request_id] = (messages, result)
            if not self.model:
                self.record(messages, result, snapshot=snapshot)
            return result

    def drain_session(self, session):
        while True:
            with session.state_lock:
                if not session.queue:
                    session.draining = False
                    return
                turn, messages, reply = session.queue.popleft()
                known = [{"id": key, "label": label} for key, label in list(session.episodes.items())[-20:]]
            extraction = self.analyze(messages, known)
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
                "reply": reply, "extraction": extraction, "analysis_status": status,
            }, snapshot=snapshot)

    @staticmethod
    def collect_indices(episodes, turn, links):
        indices = []
        for link in links:
            episode = link["episode_ref"]
            if episode.startswith("new:"):
                episode = f"t{turn}-{episode[4:]}"
                episodes.setdefault(episode, link["episode_label"] or f"Épisode du tour {turn}")
            elif episode not in episodes:
                episode = "unknown"
            indices.append({
                "dimension_id": link["dimension_id"], "relation": link["relation"],
                "strength": link["strength"], "episode_id": episode,
                "source_refs": [f"t{turn}:{item}" for item in link["observation_ids"]],
            })
        return indices


class ConversationHandler(BaseHTTPRequestHandler):
    def __init__(self, *args, service):
        self.service = service
        super().__init__(*args)

    def send_content(self, status, content, media_type):
        self.send_response(status)
        self.send_header("Content-Type", f"{media_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def send_json(self, status, value):
        self.send_content(status, json.dumps(value, ensure_ascii=False).encode(), "application/json")

    def do_GET(self):
        if self.path == "/api/conversation/opening":
            self.send_json(200, OPENING)
        elif self.path == "/api/conversation/mode":
            self.send_json(200, {"model": self.service.model})
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
            self.send_content(200, (DIRECTORY / "static" / filename).read_bytes(), media_type)
        else:
            self.send_json(404, {"detail": "Page introuvable."})

    def do_POST(self):
        if self.path == SESSION_PATH:
            session_id = self.service.create_session()
            self.log_message("Session MindSight : %s", session_id)
            self.send_json(201, {
                "session_id": session_id, "opening": OPENING, "reasoning": self.service.reasoning,
            })
            return
        if self.path != TURN_PATH:
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
