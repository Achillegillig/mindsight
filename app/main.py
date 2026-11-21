"""Point d’entrée en ligne de commande de MindSight."""

import argparse
import errno
import json
import os
import subprocess
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path

from .azure_speech import DEFAULT_STYLE, DEFAULT_VOICE, synthesize
from .dialogue import CONFIG, DIRECTORY, OPENING
from .openrouter import DEFAULT_MODEL
from .server import RECORD_PATH, ConversationHandler


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
    data = json.dumps({"opening": OPENING, "replies": CONFIG["demo_replies"]}, ensure_ascii=False)
    data = data.replace("<", "\\u003c")
    page = page.replace('<link rel="stylesheet" href="/static/chat.css">', f"<style>{styles}</style>")
    for filename in ("voice.js", "chat.js"):
        page = page.replace(f'<script defer src="/static/{filename}"></script>', "")
    page = page.replace(
        "</body>",
        f'<script id="demo-data" type="application/json">{data}</script>\n<script>{voices}</script>\n<script>{script}</script>\n</body>',
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
        handler = partial(
            ConversationHandler,
            model=None if args.simulate else args.model,
            api_key=api_key,
            speech=speech,
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
            if args.simulate:
                print("Mode — conversation simulée.", flush=True)
            else:
                print(f"Mode — OpenRouter, modèle {args.model}.", flush=True)
            if args.record:
                print(f"Journal de test — {RECORD_PATH}", flush=True)
            if args.open:
                open_firefox(url)
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
