"""Historique, configuration et relances du chat."""

import json
from pathlib import Path

DIRECTORY = Path(__file__).parent
PROMPTS_PATH = DIRECTORY / "prompts.json"
CONFIG = json.loads(PROMPTS_PATH.read_text(encoding="utf-8"))
OPENING = {"role": "assistant", "content": CONFIG["opening"]}


class PromptError(ValueError):
    pass


def validate_messages(payload):
    messages = payload.get("messages") if isinstance(payload, dict) else None
    if not isinstance(messages, list) or len(messages) < 2 or len(messages) % 2:
        raise ValueError("Historique de conversation invalide.")
    if messages[0] != OPENING:
        raise ValueError("Question d’ouverture invalide.")
    for index, message in enumerate(messages):
        role = "user" if index % 2 else "assistant"
        if not isinstance(message, dict) or message.get("role") != role:
            raise ValueError("Ordre des messages invalide.")
        content = message.get("content")
        if not isinstance(content, str) or not 1 <= len(content.strip()) <= 2000:
            raise ValueError("Message invalide.")
    return [{"role": message["role"], "content": message["content"].strip()} for message in messages]


def demo_reply(messages):
    replies = CONFIG["demo_replies"]
    return replies[(len(messages) // 2 - 1) % len(replies)]


def read_system_prompt():
    try:
        prompt = json.loads(PROMPTS_PATH.read_text(encoding="utf-8"))["system_prompt"]
        if isinstance(prompt, str) and prompt.strip():
            return prompt
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise PromptError("Vérifie le préprompt dans app/prompts.json.") from error
    raise PromptError("Vérifie le préprompt dans app/prompts.json.")
