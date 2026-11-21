"""Point d’entrée en ligne de commande de MindSight."""

import argparse
import errno
import json
import os
import socket
import subprocess
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path

from .azure_speech import DEFAULT_STYLE, DEFAULT_VOICE, synthesize
from .dialogue import CONFIG, DIRECTORY, OPENING, SKIP_PATTERN
from .openrouter import DEFAULT_MODEL


def config_value(name):
    environment_value = os.environ.get(name, "").strip()
    if environment_value:
        return environment_value

    env_path = DIRECTORY.parent / ".env"
    if env_path.is_file():
        for line in env_path.read_text(encoding="utf-8-sig").splitlines():
            assignment, separator, value = line.partition("=")
            if separator and assignment.strip().removeprefix("export ").strip() == name:
                value = value.strip()
                if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
                    value = value[1:-1]
                return value.strip()
    return ""


def export_demo(destination):
    static = DIRECTORY / "static"
    page = (static / "index.html").read_text(encoding="utf-8")
    styles = (static / "chat.css").read_text(encoding="utf-8")
    voices = (static / "voice.js").read_text(encoding="utf-8")
    script = (static / "chat.js").read_text(encoding="utf-8")
    data = json.dumps({
        "opening": OPENING, "questions": CONFIG["questions"], "replies": CONFIG["demo_replies"],
        "closing": CONFIG["closing"], "skipPattern": SKIP_PATTERN,
    }, ensure_ascii=False)
    data = data.replace("<", "\\u003c")
    page = page.replace('<link rel="stylesheet" href="/static/chat.css">', f"<style>{styles}</style>")
    for filename in ("voice.js", "chat.js"):
        page = page.replace(f'<script defer src="/static/{filename}"></script>', "")
    page = page.replace(
        "</body>",
        f'<script id="demo-data" type="application/json">{data}</script>\n<script>{voices}</script>\n<script>{script}</script>\n</body>',
    )
    destination.write_text(page, encoding="utf-8")


class LocalHTTPServer(ThreadingHTTPServer):
    def server_bind(self):
        if os.name == "nt":
            self.allow_reuse_address = False
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def create_server(handler, port=8000):
    try:
        return LocalHTTPServer(("127.0.0.1", port), handler)
    except OSError as error:
        address_busy = error.errno == errno.EADDRINUSE or getattr(error, "winerror", None) in (10013, 10048)
        if not port or not address_busy:
            raise
        return LocalHTTPServer(("127.0.0.1", 0), handler)


def open_firefox(url):
    environment = os.environ.copy()
    environment.pop("OPENROUTER_API_KEY", None)
    environment.pop("AZURE_SPEECH_KEY", None)
    try:
        subprocess.Popen(["firefox", url], env=environment)
    except OSError:
        print(f"Firefox n’a pas pu être lancé. Ouvre {url} dans ton navigateur.", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Lancer la conversation MindSight.")
    parser.add_argument("--export", type=Path, help="Générer une démo HTML ouvrable sans serveur.")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Identifiant du modèle OpenRouter.")
    parser.add_argument("--simulate", action="store_true", help="Utiliser les relances préparées.")
    parser.add_argument("--open", action="store_true", help="Ouvrir Firefox dès que le serveur écoute.")
    parser.add_argument("--record", action="store_true", help="Enregistrer les tours dans test-results.jsonl.")
    parser.add_argument("--reasoning", action="store_true", help="Afficher les indices et les décisions d’attribution dans le chat.")
    parser.add_argument("--port", type=int, default=8000, help="Port du chat local (0 pour un port libre).")
    parser.add_argument("--mcp-port", type=int, default=8001, help="Port MCP local (0 pour un port libre).")
    args = parser.parse_args()
    if args.export:
        export_demo(args.export)
        print(f"Démo générée dans {args.export.resolve()}")
    else:
        api_key = "" if args.simulate else config_value("OPENROUTER_API_KEY")
        if not args.simulate and not api_key:
            parser.error("Renseigne OPENROUTER_API_KEY dans .env ou utilise --simulate.")
        speech_key = config_value("AZURE_SPEECH_KEY")
        speech_region = config_value("AZURE_SPEECH_REGION")
        voice = config_value("AZURE_SPEECH_VOICE") or DEFAULT_VOICE
        style = config_value("AZURE_SPEECH_STYLE") or (DEFAULT_STYLE if voice == DEFAULT_VOICE else None)
        speech = None
        if speech_key and speech_region:
            speech = partial(synthesize, speech_key, speech_region, voice, style=style)

        os.environ.setdefault("HAYSTACK_TELEMETRY_ENABLED", "false")
        from .mcp_server import serve_mcp
        from .quantification import load_catalog
        from .server import RECORD_PATH, ConversationHandler, ConversationService

        try:
            catalog = load_catalog()
        except (OSError, ValueError) as error:
            parser.exit(1, f"Catalogue de dimensions invalide : {error}\n")
        with ConversationService(
            catalog,
            model=None if args.simulate else args.model,
            api_key=api_key,
            record_path=RECORD_PATH if args.record else None,
            reasoning=args.reasoning,
        ) as service:
            try:
                handler = partial(ConversationHandler, service=service, speech=speech)
                with create_server(handler, args.port) as server, serve_mcp(service, args.mcp_port) as mcp_url:
                    url = f"http://127.0.0.1:{server.server_port}/"
                    print(f"MindSight — {url}", flush=True)
                    print(f"MCP — {mcp_url}", flush=True)
                    mode = "conversation simulée" if args.simulate else f"OpenRouter, modèle {args.model}"
                    print(f"Mode — {mode}.", flush=True)
                    if args.record:
                        print(f"Journal de test — {RECORD_PATH}", flush=True)
                    if args.open:
                        open_firefox(url)
                    server.serve_forever()
            except KeyboardInterrupt:
                pass
            except (OSError, RuntimeError, OverflowError) as error:
                parser.exit(1, f"Impossible de démarrer MindSight : {error}\n")
