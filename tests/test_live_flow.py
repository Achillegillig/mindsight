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
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from haystack_integrations.components.generators.openrouter import OpenRouterChatGenerator
from pythonosc.osc_packet import OscPacket
from pythonosc.udp_client import SimpleUDPClient

from app.dialogue import OPENING
from app.extraction import extract_turn
from app.mcp_server import serve_mcp
from app.quantification import load_catalog
from app.server import ConversationHandler, ConversationService
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
        if "observations" not in payload:
            if answer == "J’ai dit que je préférais la seconde option.":
                self.gate.wait(8)
            data = {"observations": [{
                "label": "Épisode", "quote": answer, "kind": "action",
                "subject": "participant", "mode": "vecu",
            }]}
        elif answer == "Échec de l’interprétation.":
            data = {"unexpected": []}
        else:
            replay = answer.startswith("Dans le même projet")
            relation = "contre_indice" if "tais" in answer else "appui"
            episode_ref = payload["known_episodes"][0]["id"] if replay else "new:episode"
            data = {"dimensions": [{
                "dimension_id": "affirmation_de_soi", "reading": "Position exprimée dans cet épisode.",
                "relation": relation, "strength": "indirect" if "atelier" in answer else "direct",
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

            def extractor(*args, **kwargs):
                factory = partial(OpenRouterChatGenerator, api_base_url=provider_url)
                return extract_turn(*args, **kwargs, generator_factory=factory)

            with ConversationService(load_catalog(), model="fake/local", api_key="fixture",
                                     record_path=record_path, reasoning=True, extractor=extractor,
                                     dialogue=lambda *_: "Et ensuite ?") as service:
                handler = partial(ConversationHandler, service=service)
                with serving(handler) as chat_url, serve_mcp(service, 0) as mcp_url:
                    snapshot = self.exercise_conversation(service, chat_url, mcp_url, release, provider_requests)

            entries = [json.loads(line) for line in record_path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual([entry["turn"] for entry in entries], [1, 2, 3, 4, 5])
            self.assertEqual({entry["session_id"] for entry in entries}, {snapshot["session_id"]})
            self.assertEqual([entry["quantification"]["revision"] for entry in entries], [1, 2, 3, 4, 5])
            first = entries[0]
            self.assertEqual(first["extraction"]["observations"][0]["quote"], "J’ai dit que je préférais la seconde option.")
            self.assertEqual(first["extraction"]["dimensions"][0]["dimension_id"], "affirmation_de_soi")
            self.assertEqual(first["quantification"]["scope"], "session")
            initiative = next(item for item in first["quantification"]["dimensions"]
                              if item["id"] == "affirmation_de_soi")
            self.assertEqual(initiative["appui"], 0.5)
            self.assertEqual(initiative["source_refs"], ["t1:o1"])
            last = entries[-1]
            self.assertEqual(last["analysis_status"], "partial")
            self.assertIsNone(last["extraction"]["dimensions"])
            self.assertEqual(last["quantification"]["dimensions"], snapshot["dimensions"])

    def test_record_without_session_quantifies_the_single_turn(self):
        extraction = {"dimensions": [{
            "dimension_id": "affirmation_de_soi", "relation": "appui", "strength": "direct",
            "episode_ref": "new:episode", "episode_label": "Réunion", "observation_ids": ["o1"],
        }]}
        with TemporaryDirectory() as directory:
            record_path = Path(directory) / "test-results.jsonl"
            with ConversationService(load_catalog(), model="fake/local", record_path=record_path,
                                     extractor=lambda *args, **kwargs: extraction,
                                     dialogue=lambda *_: "Et ensuite ?") as service:
                service.process_legacy_turn([OPENING, {"role": "user", "content": "J’ai dit quelle option je préférais."}])
            entry = json.loads(record_path.read_text(encoding="utf-8"))
        self.assertEqual(entry["quantification"]["scope"], "turn")
        self.assertEqual(entry["analysis_status"], "ready")
        initiative = next(item for item in entry["quantification"]["dimensions"]
                          if item["id"] == "affirmation_de_soi")
        self.assertEqual(initiative["appui"], 0.5)

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
            first, result = send("J’ai dit que je préférais la seconde option.", "request-1")
            self.assertEqual(result["analysis_status"], "pending")
            self.assertEqual(post(turn_url, first), result)
            self.assertEqual(service.get_snapshot(session_id)["revision"], 0)
        finally:
            release.set()
        self.assertEqual(wait_for_turn(service, session_id, 1)["analysis_status"], "ready")
        send("Dans le même projet, j’ai dit laquelle je préférais.", "request-2")
        send("Dans un atelier, j’ai orienté le choix vers mon format préféré.", "request-3")
        send("Sur un autre projet, je me tais malgré mon désaccord.", "request-4")
        send("Échec de l’interprétation.", "request-5")
        snapshot = wait_for_turn(service, session_id, 5)
        initiative = next(item for item in snapshot["dimensions"] if item["id"] == "affirmation_de_soi")
        self.assertEqual(snapshot["revision"], 5)
        self.assertEqual(snapshot["analysis_status"], "partial")
        self.assertEqual(initiative["appui"], 0.6)
        self.assertEqual(initiative["contre_appui"], 0.5)
        self.assertEqual(initiative["episode_count"], 3)
        self.assertEqual(snapshot["observations"]["t1:o1"]["quote"], "J’ai dit que je préférais la seconde option.")
        self.assertEqual(len(provider_requests), 10)

        with urlopen(chat_url + f"/api/conversation/session/{session_id}/reasoning", timeout=5) as response:
            trace = json.load(response)
        self.assertEqual(trace["analysis_status"], "partial")
        self.assertEqual([item["turn"] for item in trace["turns"]], [1, 2, 3, 4, 5])
        self.assertEqual(trace["turns"][0]["episode_ids"], trace["turns"][1]["episode_ids"])
        self.assertEqual(trace["turns"][0]["extraction"]["trace"]["observation_candidates"], 1)
        attribution = next(item for item in trace["dimensions"] if item["id"] == "affirmation_de_soi")
        self.assertEqual(attribution["family"], "Fonctionnement relationnel")
        self.assertEqual(attribution["calculation"]["support_total"], 1.5)
        self.assertEqual(attribution["calculation"]["counter_total"], 1.0)
        self.assertEqual(attribution["appui"], initiative["appui"])

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
                {"dimension": "affirmation_de_soi", "signal": "appui", "address": "/ouverture"},
                {"dimension": "affirmation_de_soi", "signal": "contre_appui", "address": "/nuance"},
            ]
            with SimpleUDPClient("127.0.0.1", receiver.getsockname()[1]) as osc:
                asyncio.run(bridge(mcp_url, session_id, channels, osc, once=True))
            messages = [OscPacket(receiver.recv(1024)).messages[0].message for _ in channels]
        self.assertEqual([item.address for item in messages], ["/ouverture", "/nuance"])
        self.assertAlmostEqual(messages[0].params[0], 0.6)
        self.assertAlmostEqual(messages[1].params[0], 0.5)
        return snapshot
