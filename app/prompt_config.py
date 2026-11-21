"""Lecture des textes et des consignes envoyés aux modèles."""

import json
from pathlib import Path

DIRECTORY = Path(__file__).parent


def read_prompts():
    return json.loads((DIRECTORY / "prompts.json").read_text(encoding="utf-8"))
