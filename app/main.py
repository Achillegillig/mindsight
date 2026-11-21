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

from .dialogue import CONFIG, DIRECTORY, OPENING
from .openrouter import DEFAULT_MODEL

def openrouter_key():
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if key:
        return key

    env_path = DIRECTORY.parent / ".env"
    if env_path.is_file():
        for line in env_path.read_text(encoding="utf-8-sig").splitlines():
            name, separator, value = line.partition("=")
            if separator and name.strip().removeprefix("export ").strip() == "OPENROUTER_API_KEY":
                value = value.strip()
                if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
                    value = value[1:-1]
                return value.strip()
    return ""


def export_demo(destination):
    static = DIRECTORY / "static"
    page = (static / "index.html").read_text(encoding="utf-8")
    styles = (static / "chat.css").read_text(encoding="utf-8")
    script = (static / "chat.js").read_text(encoding="utf-8")
    data = json.dumps({"opening": OPENING, "replies": CONFIG["demo_replies"]}, ensure_ascii=False)
    data = data.replace("<", "\\u003c")
    page = page.replace('<link rel="stylesheet" href="/static/chat.css">', f"<style>{styles}</style>")
    page = page.replace('<script type="module" src="/static/chat.js"></script>', "")
    page = page.replace(
        "</body>",
        f'<script id="demo-data" type="application/json">{data}</script>\n<script>{script}</script>\n</body>',
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
    parser.add_argument("--port", type=int, default=8000, help="Port du chat local (0 pour un port libre).")
    parser.add_argument("--mcp-port", type=int, default=8001, help="Port MCP local (0 pour un port libre).")
    args = parser.parse_args()
    if args.export:
        export_demo(args.export)
        print(f"Démo générée dans {args.export.resolve()}")
    else:
        api_key = "" if args.simulate else openrouter_key()
        if not args.simulate and not api_key:
            parser.error("Renseigne OPENROUTER_API_KEY dans .env ou utilise --simulate.")
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
        ) as service:
            try:
                handler = partial(ConversationHandler, service=service)
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
