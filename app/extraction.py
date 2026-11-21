"""Analyse d'un tour avec deux passes Haystack et des citations vérifiables."""

import json
import re
from time import monotonic

from haystack import Pipeline
from haystack.components.builders import ChatPromptBuilder
from haystack.core.errors import PipelineRuntimeError
from haystack.dataclasses import ChatMessage
from haystack.utils import Secret
from haystack_integrations.components.generators.openrouter import OpenRouterChatGenerator

from .prompt_config import read_prompts
from .quantification import load_catalog

EXTRACTION_PROMPTS = read_prompts()["extraction"]
OBSERVE = "\n".join(EXTRACTION_PROMPTS["observe"])
INTERPRET = "\n".join(EXTRACTION_PROMPTS["interpret"])

KINDS = {"image", "ressenti", "action", "preference", "raisonnement", "relation", "valeur", "autre"}
SUBJECTS = {"participant", "tiers", "personnage", "incertain"}
MODES = {"vecu", "declaration", "fiction", "citation", "hypothetique"}


class ExtractionError(RuntimeError):
    pass


def run_pass(generator, prompt, payload):
    pipeline = Pipeline()
    pipeline.add_component("prompt", ChatPromptBuilder(
        template=[ChatMessage.from_system(prompt), ChatMessage.from_user("{{ payload }}")],
        required_variables=["payload"],
    ))
    pipeline.add_component("generator", generator)
    pipeline.connect("prompt.prompt", "generator.messages")
    try:
        result = pipeline.run({"prompt": {"payload": json.dumps(payload, ensure_ascii=False)}})
        reply = result["generator"]["replies"][0]
        if reply.meta.get("finish_reason") == "length":
            raise ValueError("Sortie tronquée.")
        parsed = json.loads(reply.text)
    except (PipelineRuntimeError, KeyError, IndexError, TypeError, ValueError, RecursionError) as error:
        raise ExtractionError("La réponse du modèle d’analyse est indisponible ou invalide.") from error
    if not isinstance(parsed, dict):
        raise ExtractionError("Un objet JSON d’analyse est attendu.")
    return parsed


def read_items(payload, key, limit):
    items = payload.get(key)
    if not isinstance(items, list):
        raise ExtractionError(f"Tableau d’analyse manquant : {key}.")
    return (item for item in items[:limit] if isinstance(item, dict))


def grounded_observations(payload, answer):
    observations = []
    seen = set()
    for item in read_items(payload, "observations", 12):
        quote, label = item.get("quote"), item.get("label")
        if not isinstance(quote, str) or not quote.strip() or not isinstance(label, str):
            continue
        start = answer.find(quote)
        if start < 0 or answer.find(quote, start + 1) >= 0 or not 0 < len(label.strip()) <= 80:
            continue
        if any(not isinstance(item.get(key), str) or item[key] not in valid
               for key, valid in (("kind", KINDS), ("subject", SUBJECTS), ("mode", MODES))):
            continue
        key = (quote, item["kind"], item["subject"], item["mode"])
        if key in seen:
            continue
        seen.add(key)
        observations.append({
            "id": f"o{len(observations) + 1}", "quote": quote, "label": label.strip(),
            "start": start, "end": start + len(quote),
            **{key: item[key] for key in ("kind", "subject", "mode")},
        })
    return observations


def grounded_dimensions(payload, observations, catalog, known_episodes):
    by_id = {item["id"]: item for item in observations}
    profiles = {item["id"]: item for item in catalog.dimensions}
    known = {item["id"] for item in known_episodes}
    dimensions = []
    for item in read_items(payload, "dimensions", 16):
        dimension_id, ids = item.get("dimension_id"), item.get("observation_ids")
        reading, episode = item.get("reading"), item.get("episode_ref")
        if not isinstance(dimension_id, str) or dimension_id not in profiles:
            continue
        if not isinstance(ids, list) or not all(isinstance(key, str) and key in by_id for key in ids):
            continue
        spans = sorted({(by_id[key]["end"], by_id[key]["start"]) for key in ids})
        end = count = 0
        for stop, start in spans:
            if start >= end:
                count += 1
                end = stop
        profile = profiles[dimension_id]
        if count < profile.get("min_observations", 1) or not isinstance(reading, str) or not 0 < len(reading.strip()) <= 350:
            continue
        strength = item.get("strength")
        if item.get("relation", "appui") != "appui" or strength not in ("direct", "indirect"):
            continue
        participant = [by_id[key] for key in ids if by_id[key]["subject"] == "participant"]
        has_lived_evidence = any(obs["mode"] in ("vecu", "declaration") for obs in participant)
        if not has_lived_evidence:
            if not (profile.get("allow_fiction")
                    and any(obs["mode"] == "fiction" for obs in participant)):
                continue
            strength = "indirect"
        if not isinstance(episode, str) or (episode not in known and not re.fullmatch(r"new:[a-zA-Z0-9_-]{1,24}", episode)):
            episode = "unknown"
        label = item.get("episode_label")
        dimensions.append({
            "dimension_id": dimension_id, "observation_ids": list(dict.fromkeys(ids)),
            "reading": reading.strip(), "episode_ref": episode,
            "episode_label": label.strip()[:100] if isinstance(label, str) else "",
            "strength": strength,
        })
    return dimensions


def generate(api_key, model, prompt, payload, timeout, generator_factory):
    if timeout <= 0:
        raise ExtractionError("Le délai d’analyse du tour a expiré.")
    generator = generator_factory(
        api_key=Secret.from_token(api_key), model=model, timeout=timeout, max_retries=0,
        generation_kwargs={
            "response_format": {"type": "json_object"},
            "max_tokens": 1800,
            "reasoning": {"enabled": False},
        },
    )
    return run_pass(generator, prompt, payload)


def observe_turn(api_key, model, question, answer, *, timeout=5.0,
                 include_trace=False, generator_factory=OpenRouterChatGenerator):
    observed = generate(api_key, model, OBSERVE, {
        "question": question, "answer": answer,
    }, timeout, generator_factory)
    observations = grounded_observations(observed, answer)
    result = {
        "visual_elements": [
            {"label": item["label"], "quote": item["quote"]} for item in observations
            if item["kind"] == "image"
        ][:3],
        "expressed_feelings": [
            {"label": item["label"], "quote": item["quote"]} for item in observations
            if item["kind"] == "ressenti" and item["subject"] == "participant"
            and item["mode"] in ("vecu", "declaration")
        ][:3],
        "observations": observations,
        "dimensions": [],
    }
    if include_trace:
        result["trace"] = {
            "observation_candidates": len(observed["observations"]),
            "interpretation_candidates": None,
        }
    return result


def extract_turn(api_key, model, question, answer, *, catalog=None, known_episodes=(),
                 include_trace=False, timeout=10.0, generator_factory=OpenRouterChatGenerator,
                 observed=None):
    catalog = catalog if catalog is not None else load_catalog()
    deadline = monotonic() + timeout
    result = observed if observed is not None else observe_turn(
        api_key, model, question, answer, timeout=timeout / 2,
        include_trace=include_trace, generator_factory=generator_factory,
    )
    observations = result["observations"]
    if observations:
        try:
            interpreted = generate(api_key, model, INTERPRET, {
                "question": question, "answer": answer, "observations": observations,
                "known_episodes": known_episodes,
                "catalog": [
                    {key: value for key, value in item.items() if key != "quantification"}
                    for item in catalog.dimensions
                ],
            }, deadline - monotonic(), generator_factory)
            result["dimensions"] = grounded_dimensions(interpreted, observations, catalog, known_episodes)
            if "trace" in result:
                result["trace"]["interpretation_candidates"] = len(interpreted["dimensions"])
        except ExtractionError:
            result["dimensions"] = None
    return result
