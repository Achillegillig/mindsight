"""Point d’entrée en ligne de commande de MindSight."""

import argparse
import errno
import json
import os
import subprocess
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path

from .dialogue import CONFIG, DIRECTORY, OPENING
from .openrouter import DEFAULT_MODEL
from .server import RECORD_PATH, ConversationHandler

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


def create_server(handler):
    try:
        return ThreadingHTTPServer(("127.0.0.1", 8000), handler)
    except OSError as error:
        if error.errno != errno.EADDRINUSE:
            raise
        return ThreadingHTTPServer(("127.0.0.1", 0), handler)


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
    args = parser.parse_args()
    if args.export:
        export_demo(args.export)
        print(f"Démo générée dans {args.export.resolve()}")
    else:
        api_key = "" if args.simulate else openrouter_key()
        if not args.simulate and not api_key:
            parser.error("Renseigne OPENROUTER_API_KEY dans .env ou utilise --simulate.")
        handler = partial(
            ConversationHandler,
            model=None if args.simulate else args.model,
            api_key=api_key,
            record_path=RECORD_PATH if args.record else None,
        )
        try:
            server = create_server(handler)
        except PermissionError:
            parser.exit(
                1,
                "Impossible d’ouvrir un port local dans ce terminal. "
                "Lance la commande dans le Terminal de Linux Mint, hors de Codex.\n",
            )
        except OSError as error:
            parser.exit(1, f"Impossible de démarrer MindSight : {error.strerror}.\n")
        with server:
            url = f"http://127.0.0.1:{server.server_port}/"
            print(f"MindSight — {url}", flush=True)
            if args.record:
                print(f"Journal de test — {RECORD_PATH}", flush=True)
            if args.open:
                open_firefox(url)
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
