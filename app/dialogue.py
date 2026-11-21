"""Historique, configuration et relances du chat."""

import json
import re

from .prompt_config import read_prompts

CONFIG = read_prompts()["conversation"]
QUESTIONS = CONFIG["questions"]
OPENING = {"role": "assistant", "content": QUESTIONS[0]}
CLOSING = CONFIG["closing"]
FOLLOWUP_STEPS = ("detail", "experience")
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


def next_step(messages, *, has_evidence=False):
    assistant_messages = [item["content"] for item in messages[::2]]
    question_positions = [
        index for index, content in enumerate(assistant_messages) if content in QUESTIONS
    ]
    asked = len(question_positions)
    followups = len(assistant_messages) - question_positions[-1] - 1
    answer = messages[-1]["content"]
    prepared = CONFIG["demo_replies"]
    if (not has_evidence and not re.match(SKIP_PATTERN, answer, re.IGNORECASE)
            and followups < len(prepared)):
        return FOLLOWUP_STEPS[followups], prepared[followups]
    if asked < len(QUESTIONS):
        return "question", QUESTIONS[asked]
    return "done", CLOSING


def read_followup_prompt(step):
    try:
        prompts = read_prompts()["conversation"]["followup_prompts"]
        common, instruction = prompts["common"], prompts[step]
        if all(isinstance(text, str) and text.strip() for text in (common, instruction)):
            return f"{common.strip()}\n{instruction.strip()}"
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise PromptError("Vérifie les préprompts de relance dans app/prompts.json.") from error
    raise PromptError("Vérifie les préprompts de relance dans app/prompts.json.")
