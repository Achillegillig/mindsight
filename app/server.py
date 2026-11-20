"""Routes HTTP et coordination des deux traitements d’un tour."""

import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler
from threading import Lock

from .dialogue import DIRECTORY, OPENING, PromptError, demo_reply, read_system_prompt, validate_messages
from .extraction import extract_turn
from .openrouter import OpenRouterError, generate_reply

STATIC = {
    "/": ("index.html", "text/html"),
    "/static/chat.css": ("chat.css", "text/css"),
    "/static/chat.js": ("chat.js", "text/javascript"),
}
TURN_PATH = "/api/conversation/turn"
MAX_BODY_BYTES = 256 * 1024
RECORD_PATH = DIRECTORY.parent / "test-results.jsonl"
RECORD_LOCK = Lock()


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


class ConversationHandler(BaseHTTPRequestHandler):
    def __init__(self, *args, model=None, api_key=None, record_path=None):
        self.model = model
        self.api_key = api_key
        self.record_path = record_path
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
            self.send_json(200, {"model": self.model})
        elif self.path in STATIC:
            filename, media_type = STATIC[self.path]
            self.send_content(200, (DIRECTORY / "static" / filename).read_bytes(), media_type)
        else:
            self.send_json(404, {"detail": "Page introuvable."})

    def do_POST(self):
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
            result = self.process_turn(messages)
        except PromptError as error:
            self.send_json(500, {"detail": str(error)})
            return
        except OpenRouterError as error:
            self.send_json(502, {"detail": str(error)})
            return
        if self.record_path is not None:
            try:
                record_turn(self.record_path, messages, result)
            except OSError as error:
                self.log_error("Écriture du journal de test impossible : %s", error)
        self.send_json(200, result)


    def process_turn(self, messages):
        if not self.model:
            return {"reply": demo_reply(messages), "extraction": None}

        prompt = read_system_prompt()
        question = messages[-2]["content"]
        answer = messages[-1]["content"]
        with ThreadPoolExecutor(max_workers=1) as pool:
            extraction_job = pool.submit(extract_turn, self.api_key, self.model, question, answer)
            reply = generate_reply(self.api_key, self.model, prompt, messages)
            try:
                extraction = extraction_job.result()
            except (OpenRouterError, ValueError, RecursionError):
                self.log_error("Extraction indisponible pour ce tour.")
                extraction = None

        return {"reply": reply, "extraction": extraction}
