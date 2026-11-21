"""Historique, configuration et relances du chat."""

import json
import re
from pathlib import Path

DIRECTORY = Path(__file__).parent
PROMPTS_PATH = DIRECTORY / "prompts.json"
CONFIG = json.loads(PROMPTS_PATH.read_text(encoding="utf-8"))
QUESTIONS = CONFIG["questions"]
OPENING = {"role": "assistant", "content": QUESTIONS[0]}
CLOSING = CONFIG["closing"]
SKIP_PATTERN = r"^(?:je (?:ne )?sais pas[.!?…]*$|aucune idée[.!?…]*$|(?:je )?passe[.!?…]*$|je préfère (?:passer|ne pas répondre)\b|je ne ressens rien\b)"


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


def next_step(messages, *, has_feeling=False):
    assistant_messages = [item["content"] for item in messages[::2]]
    question_positions = [
        index for index, content in enumerate(assistant_messages) if content in QUESTIONS
    ]
    asked = len(question_positions)
    followups = len(assistant_messages) - question_positions[-1] - 1
    answer = messages[-1]["content"]
    prepared = CONFIG["demo_replies"]
    if (not has_feeling and not re.match(SKIP_PATTERN, answer, re.IGNORECASE)
            and followups < len(prepared)):
        return "followup", prepared[followups]
    if asked < len(QUESTIONS):
        return "question", QUESTIONS[asked]
    return "done", CLOSING


def read_system_prompt():
    try:
        prompt = json.loads(PROMPTS_PATH.read_text(encoding="utf-8"))["system_prompt"]
        if isinstance(prompt, str) and prompt.strip():
            return prompt
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise PromptError("Vérifie le préprompt dans app/prompts.json.") from error
    raise PromptError("Vérifie le préprompt dans app/prompts.json.")
