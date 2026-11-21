import asyncio
from contextlib import contextmanager
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from queue import Queue
import socket
import subprocess
import sys
from tempfile import TemporaryDirectory
from threading import Event, Thread
from time import monotonic, sleep
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from haystack_integrations.components.generators.openrouter import OpenRouterChatGenerator
from pythonosc.osc_packet import OscPacket
from pythonosc.udp_client import SimpleUDPClient

from app.azure_speech import DEFAULT_STYLE, DEFAULT_VOICE, synthesize
from app.dialogue import CLOSING, OPENING, QUESTIONS
from app.extraction import extract_turn, observe_turn
from app.mcp_server import serve_mcp
from app.quantification import load_catalog
from app.server import ConversationHandler, ConversationService, TurnConflict
from visualization.mcp_to_osc import bridge


@contextmanager
def serving(handler):
    with ThreadingHTTPServer(("127.0.0.1", 0), handler) as server:
        thread = Thread(target=server.serve_forever)
        thread.start()
        try:
            yield f"http://127.0.0.1:{server.server_port}"
        finally:
            server.shutdown()
            thread.join()


def post(url, data):
    request = Request(url, json.dumps(data).encode(), {"Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(request, timeout=10) as response:
            return json.load(response)
    except HTTPError as error:
        error.close()
        raise


def wait_for_turn(service, session_id, turn):
    deadline = monotonic() + 10
    while monotonic() < deadline:
        snapshot = service.get_snapshot(session_id)
        if snapshot["through_turn"] >= turn:
            return snapshot
        sleep(0.02)
    raise AssertionError(f"L’analyse du tour {turn} ne s’est pas terminée.")


class FixtureOpenRouter(BaseHTTPRequestHandler):
    def __init__(self, *args, gate, requests):
        self.gate = gate
        self.requests = requests
        super().__init__(*args)

    def do_POST(self):
        request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        payload = json.loads(request["messages"][-1]["content"])
        answer = payload["answer"]
        self.requests.append(payload)
        if "observations" in payload and answer == "Je me sentais capable de porter le projet et ça me rassurait.":
            self.gate.wait(8)
        if "observations" not in payload:
            data = {"observations": [{
                "label": "Épisode", "quote": answer,
                "kind": "ressenti" if "soulagé" in answer or "rassurait" in answer else "action",
                "subject": "participant", "mode": "vecu",
            }]}
        elif answer == "Échec de l’interprétation.":
            data = {"unexpected": []}
        else:
            replay = answer.startswith("Dans le même projet")
            episode_ref = payload["known_episodes"][0]["id"] if replay else "new:episode"
            data = {"dimensions": [{
                "dimension_id": "confiance_en_soi", "reading": "Confiance dans ses capacités exprimée dans cet épisode.",
                "strength": "indirect" if "atelier" in answer else "direct",
                **({"relation": "contre_indice"} if "doutais" in answer else {}),
                "observation_ids": ["o1"], "episode_ref": episode_ref, "episode_label": answer,
            }]}
        body = json.dumps({
            "id": "fixture", "object": "chat.completion", "created": 1, "model": request["model"],
            "choices": [{"index": 0, "finish_reason": "stop", "message": {
                "role": "assistant", "content": json.dumps(data, ensure_ascii=False),
            }}],
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class LiveFlowTests(unittest.TestCase):
    def test_speech_route_calls_azure_synthesis_and_returns_audio(self):
        speech = partial(synthesize, "fixture-key", "westeurope", DEFAULT_VOICE, style=DEFAULT_STYLE)
        with ConversationService(load_catalog(), reasoning=True) as service:
            handler = partial(ConversationHandler, service=service, speech=speech)
            with serving(handler) as chat_url, patch("app.azure_speech.urlopen") as azure:
                response = azure.return_value.__enter__.return_value
                response.status = 200
                response.read.return_value = b"fixture-mp3"
                with urlopen(chat_url + "/api/conversation/mode", timeout=5) as response:
                    self.assertTrue(json.load(response)["azureSpeech"])
                request = Request(
                    chat_url + "/api/speech", b'{"text":" A & B ? "}',
                    {"Content-Type": "application/json"}, method="POST",
                )
                with urlopen(request, timeout=5) as response:
                    self.assertEqual(response.headers.get_content_type(), "audio/mpeg")
                    self.assertEqual(response.read(), b"fixture-mp3")
                azure.assert_called_once()
                request_to_azure = azure.call_args.args[0]
                self.assertEqual(request_to_azure.full_url,
                                 "https://westeurope.tts.speech.microsoft.com/cognitiveservices/v1")
                self.assertIn(b"A &amp; B ?", request_to_azure.data)

    def test_simulation_starts_through_the_cli(self):
        with subprocess.Popen(
            [sys.executable, "-X", "utf8", "-m", "app.main", "--simulate", "--reasoning",
             "--port", "0", "--mcp-port", "0"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8",
        ) as process:
            lines = Queue()

            def read_output():
                for line in process.stdout:
                    lines.put(line.strip())
                lines.put("")

            Thread(target=read_output, daemon=True).start()
            try:
                urls = {}
                deadline = monotonic() + 15
                while len(urls) < 2:
                    line = lines.get(timeout=max(0, deadline - monotonic()))
                    self.assertTrue(line, "MindSight s’est arrêté au démarrage.")
                    name, separator, url = line.partition(" — ")
                    if separator and name in ("MindSight", "MCP"):
                        urls[name] = url
                session = post(urls["MindSight"] + "api/conversation/session", {})
                self.assertTrue(session["reasoning"])
                response = post(urls["MindSight"] + "api/conversation/turn", {
                    "session_id": session["session_id"], "request_id": "simulated",
                    "messages": [session["opening"], {"role": "user", "content": "Un galet."}],
                })
                self.assertTrue(response["reply"])
                self.assertEqual(response["analysis_status"], "simulated")
                trace_url = urls["MindSight"] + f"api/conversation/session/{session['session_id']}/reasoning"
                with urlopen(trace_url, timeout=5) as response:
                    reasoning = json.load(response)
                self.assertEqual(reasoning["analysis_status"], "simulated")
                self.assertEqual(reasoning["turns"], [])
                asyncio.run(bridge(urls["MCP"], session["session_id"], (), None, once=True))
            finally:
                process.terminate()
                process.wait(timeout=5)

    def test_export_contains_the_offline_chat(self):
        with TemporaryDirectory() as directory:
            output = Path(directory) / "demo.html"
            subprocess.run([sys.executable, "-m", "app.main", "--export", str(output)],
                           check=True, capture_output=True, timeout=10)
            html = output.read_text(encoding="utf-8")
        self.assertIn('id="demo-data"', html)
        self.assertIn("getReply", html)
        self.assertNotIn('src="/static/chat.js"', html)

    def test_http_haystack_mcp_and_real_osc_packet(self):
        release = Event()
        provider_requests = []
        fake_provider = partial(FixtureOpenRouter, gate=release, requests=provider_requests)
        with TemporaryDirectory() as directory, serving(fake_provider) as provider_url:
            record_path = Path(directory) / "test-results.jsonl"

            factory = partial(OpenRouterChatGenerator, api_base_url=provider_url)
            with ConversationService(load_catalog(), model="fake/local", api_key="fixture",
                                     record_path=record_path, reasoning=True,
                                     extractor=partial(extract_turn, generator_factory=factory),
                                     observer=partial(observe_turn, generator_factory=factory),
                                     dialogue=lambda *_: "Et ensuite ?") as service:
                handler = partial(ConversationHandler, service=service)
                with serving(handler) as chat_url, serve_mcp(service, 0) as mcp_url:
                    snapshot = self.exercise_conversation(service, chat_url, mcp_url, release, provider_requests)

            entries = [json.loads(line) for line in record_path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual([entry["turn"] for entry in entries], [1, 2, 3, 4, 5])
            self.assertEqual({entry["session_id"] for entry in entries}, {snapshot["session_id"]})
            self.assertEqual([entry["quantification"]["revision"] for entry in entries], [1, 2, 3, 4, 5])
            first = entries[0]
            self.assertEqual(first["extraction"]["observations"][0]["quote"], "Je me sentais capable de porter le projet et ça me rassurait.")
            self.assertEqual(first["extraction"]["dimensions"][0]["dimension_id"], "confiance_en_soi")
            self.assertEqual(first["quantification"]["scope"], "session")
            confidence = next(item for item in first["quantification"]["dimensions"]
                              if item["id"] == "confiance_en_soi")
            self.assertEqual(confidence["score"], 4)
            self.assertEqual(confidence["source_refs"], ["t1:o1"])
            self.assertEqual(entries[-2]["analysis_status"], "partial")
            self.assertIsNone(entries[-2]["extraction"]["dimensions"])
            self.assertEqual(entries[-1]["quantification"]["dimensions"], snapshot["dimensions"])

    def test_each_question_requires_its_own_feeling(self):
        def observe(*args, **kwargs):
            answer = args[-1]
            return {
                "observations": [{"id": "o1", "quote": answer}],
                "expressed_feelings": [{"label": "calme", "quote": answer}] if "calme" in answer else [],
                "dimensions": [],
            }

        with ConversationService(
            load_catalog(), model="fake/local", reasoning=True,
            observer=observe, extractor=lambda *args, **kwargs: kwargs["observed"],
            dialogue=lambda *_: "Qu’est-ce que ça t’évoque ?",
        ) as service:
            session_id = service.create_session()
            history = [OPENING]
            for turn, (text, expected) in enumerate([
                ("Je me sens calme.", QUESTIONS[1]),
                ("Un pigeon.", None),
                ("Il parlerait beaucoup.", None),
                ("De toutes les miettes.", QUESTIONS[2]),
                ("Les klaxons.", None),
                ("Surtout ceux des voitures.", None),
                ("Je préfère passer.", CLOSING),
            ], 1):
                messages = [*history, {"role": "user", "content": text}]
                result = service.process_session_turn(session_id, str(turn), messages)
                if expected is None:
                    self.assertNotIn(result["reply"], [*QUESTIONS, CLOSING])
                else:
                    self.assertEqual(result["reply"], expected)
                self.assertEqual(result["done"], expected == CLOSING)
                self.assertEqual(service.process_session_turn(session_id, str(turn), messages), result)
                history = [*messages, {"role": "assistant", "content": result["reply"]}]
            with self.assertRaises(TurnConflict):
                service.process_session_turn(session_id, "extra", [
                    *history, {"role": "user", "content": "Encore une réponse."},
                ])
            self.assertEqual(wait_for_turn(service, session_id, 7)["analysis_status"], "ready")

    def test_validated_trait_prevents_a_followup_without_repeating_analysis(self):
        answer = "Un grain de sable qui sert de refuge aux pétoncles."
        observation = {
            "observations": [{"id": "o1", "quote": answer}],
            "expressed_feelings": [],
            "dimensions": [],
        }
        extraction = {**observation, "dimensions": [{
            "dimension_id": "creativite", "strength": "indirect", "observation_ids": ["o1"],
            "episode_ref": "new:refuge", "episode_label": "Le refuge des pétoncles",
        }]}
        with patch("app.server.read_followup_prompt") as relaunch, ConversationService(
            load_catalog(), model="fixture",
            observer=lambda *args, **kwargs: observation,
        ) as service:
            with patch.object(service, "extractor", return_value=extraction) as interpret:
                session = service.create_session()
                result = service.process_session_turn(
                    session, "first", [OPENING, {"role": "user", "content": answer}],
                )
                self.assertEqual(result["reply"], QUESTIONS[1])
                snapshot = wait_for_turn(service, session, 1)
                scores = {item["id"]: item["score"] for item in snapshot["dimensions"]}
                self.assertEqual(scores["creativite"], 2)
                interpret.assert_called_once()
                relaunch.assert_not_called()

    def test_final_scores_wait_for_the_last_analysis_and_cover_the_catalog(self):
        finish_analysis = Event()
        answer = "Le courant me calme."
        observed = {
            "observations": [{"id": "o1"}],
            "expressed_feelings": [{"label": "calme", "quote": answer}],
            "dimensions": [],
        }

        def interpret(*args, **kwargs):
            finish_analysis.wait(3)
            return {**observed, "dimensions": [{
                "dimension_id": "reveur", "episode_ref": "new:image", "episode_label": "Image",
                "strength": "indirect", "relation": "appui", "observation_ids": ["o1"],
            }]}

        with ConversationService(load_catalog(), model="fixture",
                                 observer=lambda *args, **kwargs: observed,
                                 extractor=interpret) as service:
            session_id = service.create_session()
            self.assertFalse(service.get_scores(session_id)["ready"])
            try:
                history = [OPENING]
                for turn, reply in enumerate([*QUESTIONS[1:], CLOSING], 1):
                    messages = [*history, {"role": "user", "content": answer}]
                    result = service.process_session_turn(session_id, str(turn), messages)
                    self.assertEqual(result["done"], turn == 3)
                    history = [*messages, {"role": "assistant", "content": reply}]
                pending = service.get_scores(session_id)
                self.assertFalse(pending["ready"])
                self.assertEqual(pending["traits"], [])
            finally:
                finish_analysis.set()
            wait_for_turn(service, session_id, 3)
            result = service.get_scores(session_id)
            self.assertTrue(result["ready"])
            self.assertEqual(result["through_turn"], 3)
            self.assertEqual(len(result["traits"]), len(service.catalog.dimensions))
            scores = {trait["id"]: trait for trait in result["traits"]}
            self.assertEqual(scores["reveur"]["score"], 6)
            self.assertEqual(scores["humour"]["score"], 0)
            self.assertEqual(scores["humour"]["status"], "sans_indice")

    def test_simulated_session_allows_two_followups_per_question(self):
        with ConversationService(load_catalog()) as service:
            session_id = service.create_session()
            messages = [OPENING]
            questions = [OPENING["content"]]
            for turn in range(1, 10):
                messages.append({"role": "user", "content": "Un détail."})
                result = service.process_session_turn(session_id, str(turn), messages)
                self.assertEqual(result["done"], turn == 9)
                if turn in (3, 6):
                    self.assertEqual(result["reply"], QUESTIONS[turn // 3])
                messages.append({"role": "assistant", "content": result["reply"]})
                if result["reply"] in QUESTIONS:
                    questions.append(result["reply"])
            self.assertEqual(questions, QUESTIONS)
            self.assertEqual(result["reply"], CLOSING)

    def test_record_without_session_quantifies_the_single_turn(self):
        extraction = {"dimensions": [{
            "dimension_id": "confiance_en_soi", "relation": "appui", "strength": "direct",
            "episode_ref": "new:episode", "episode_label": "Réunion", "observation_ids": ["o1"],
        }]}
        with TemporaryDirectory() as directory:
            record_path = Path(directory) / "test-results.jsonl"
            with ConversationService(load_catalog(), model="fake/local", record_path=record_path,
                                     extractor=lambda *args, **kwargs: extraction,
                                     dialogue=lambda *_: "Et ensuite ?") as service:
                service.process_legacy_turn([OPENING, {"role": "user", "content": "Je savais que je pouvais mener le projet."}])
            entry = json.loads(record_path.read_text(encoding="utf-8"))
        self.assertEqual(entry["quantification"]["scope"], "turn")
        self.assertEqual(entry["analysis_status"], "ready")
        confidence = next(item for item in entry["quantification"]["dimensions"]
                          if item["id"] == "confiance_en_soi")
        self.assertEqual(confidence["score"], 4)

    def exercise_conversation(self, service, chat_url, mcp_url, release, provider_requests):
        session = post(chat_url + "/api/conversation/session", {})
        self.assertTrue(session["reasoning"])
        session_id = session["session_id"]
        turn_url = chat_url + "/api/conversation/turn"
        history = [session["opening"]]

        def send(answer, request_id):
            payload = {
                "session_id": session_id, "request_id": request_id,
                "messages": [*history, {"role": "user", "content": answer}],
            }
            result = post(turn_url, payload)
            history.extend([payload["messages"][-1], {"role": "assistant", "content": result["reply"]}])
            return payload, result

        try:
            first, result = send("Je me sentais capable de porter le projet et ça me rassurait.", "request-1")
            self.assertEqual(result["analysis_status"], "pending")
            self.assertEqual(post(turn_url, first), result)
            self.assertEqual(service.get_snapshot(session_id)["revision"], 0)
        finally:
            release.set()
        self.assertEqual(wait_for_turn(service, session_id, 1)["analysis_status"], "ready")
        send("Sur un autre projet, je doutais de mes capacités.", "request-2")
        send("Dans le même projet, je savais que je pouvais mener le travail à terme. Je suis soulagé.", "request-3")
        send("Échec de l’interprétation.", "request-4")
        send("Dans un atelier, je me suis senti capable de présenter le résultat. Je suis soulagé.", "request-5")
        snapshot = wait_for_turn(service, session_id, 5)
        confidence = next(item for item in snapshot["dimensions"] if item["id"] == "confiance_en_soi")
        self.assertEqual(snapshot["revision"], 5)
        self.assertEqual(snapshot["analysis_status"], "ready")
        self.assertEqual(confidence["score"], 6)
        self.assertNotIn("contre_appui", confidence)
        self.assertEqual(confidence["episode_count"], 2)
        self.assertEqual(snapshot["observations"]["t1:o1"]["quote"], "Je me sentais capable de porter le projet et ça me rassurait.")
        self.assertEqual(len(provider_requests), 10)

        with urlopen(chat_url + f"/api/conversation/session/{session_id}/reasoning", timeout=5) as response:
            trace = json.load(response)
        self.assertEqual(trace["analysis_status"], "ready")
        self.assertEqual([item["turn"] for item in trace["turns"]], [1, 2, 3, 4, 5])
        self.assertEqual(trace["turns"][0]["episode_ids"], trace["turns"][2]["episode_ids"])
        self.assertEqual(trace["turns"][0]["extraction"]["trace"]["observation_candidates"], 1)
        attribution = next(item for item in trace["dimensions"] if item["id"] == "confiance_en_soi")
        self.assertEqual(attribution["family"], "Rapport à soi")
        self.assertEqual(attribution["calculation"]["total_points"], 6)
        self.assertEqual(attribution["score"], confidence["score"])

        first["messages"][-1]["content"] = "Une autre réponse"
        with self.assertRaises(HTTPError) as error:
            post(turn_url, first)
        self.assertEqual(error.exception.code, 409)

        other = post(chat_url + "/api/conversation/session", {})
        self.assertEqual(service.get_snapshot(other["session_id"])["revision"], 0)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as receiver:
            receiver.bind(("127.0.0.1", 0))
            receiver.settimeout(2)
            channels = [
                {"dimension": "confiance_en_soi", "signal": "appui", "address": "/ouverture"},
            ]
            with SimpleUDPClient("127.0.0.1", receiver.getsockname()[1]) as osc:
                asyncio.run(bridge(mcp_url, session_id, channels, osc, once=True))
            messages = [OscPacket(receiver.recv(1024)).messages[0].message for _ in channels]
        self.assertEqual([item.address for item in messages], ["/ouverture"])
        self.assertAlmostEqual(messages[0].params[0], 0.6)
        return snapshot
