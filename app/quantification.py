"""Catalogue éditable et calcul déterministe des signaux de rendu."""

from collections import defaultdict
from dataclasses import dataclass
from math import isfinite
from pathlib import Path
import re

import yaml

CATALOG_PATH = Path(__file__).with_name("dimensions.yaml")
MAX_SCORE = 10


@dataclass(frozen=True)
class Catalog:
    version: int
    dimensions: tuple[dict, ...]
    weights: dict[str, float]


def number(value):
    if type(value) not in (int, float) or not isfinite(value) or value < 0:
        raise ValueError("Les réglages de quantification doivent être des nombres finis et valides.")
    return float(value)


def load_catalog(path=CATALOG_PATH):
    try:
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except yaml.YAMLError as error:
        raise ValueError("Syntaxe YAML invalide.") from error
    if not isinstance(data, dict) or type(data.get("version")) is not int or data["version"] < 1:
        raise ValueError("Le catalogue doit déclarer une version entière positive.")
    rules = data.get("quantification")
    dimensions = data.get("dimensions")
    if not isinstance(rules, dict) or not isinstance(dimensions, list) or not dimensions:
        raise ValueError("Le catalogue doit définir les dimensions et leur quantification.")
    weights = rules.get("weights")
    if not isinstance(weights, dict) or set(weights) != {"direct", "indirect"}:
        raise ValueError("Les poids direct et indirect sont requis.")
    known = set()
    for item in dimensions:
        if not isinstance(item, dict) or any(
            not isinstance(item.get(key), str) or not item[key].strip()
            for key in ("id", "label", "definition")
        ):
            raise ValueError("Chaque dimension doit avoir un identifiant, un libellé et une définition.")
        if not re.fullmatch(r"[a-z][a-z0-9_]*", item["id"]) or item["id"] in known:
            raise ValueError(f"Identifiant de dimension invalide ou répété : {item['id']}")
        known.add(item["id"])
        if not isinstance(item.get("allow_fiction", False), bool):
            raise ValueError("allow_fiction doit être un booléen.")
        minimum = item.get("min_observations", 1)
        if type(minimum) is not int or minimum < 1:
            raise ValueError("min_observations doit être un entier positif.")
        overrides = item.get("quantification", {})
        if not isinstance(overrides, dict):
            raise ValueError("Les réglages par dimension doivent former un objet.")
        overrides_weights = overrides.get("weights", {})
        if not isinstance(overrides_weights, dict) or not overrides_weights.keys() <= weights.keys():
            raise ValueError("Poids par dimension inconnus.")
        for value in overrides_weights.values():
            number(value)

    return Catalog(
        data["version"], tuple(dimensions),
        {name: number(value) for name, value in weights.items()},
    )


def quantify_dimensions(indices, catalog, *, include_calculation=False):
    """Cumule le meilleur indice de chaque épisode, avec un plafond sur 10."""
    by_dimension = defaultdict(list)
    for index in indices:
        if index.get("relation", "appui") == "appui":
            by_dimension[index["dimension_id"]].append(index)

    dimensions = []
    for dimension in catalog.dimensions:
        settings = dimension.get("quantification", {})
        weights = {**catalog.weights, **settings.get("weights", {})}
        episodes = {}
        for index in by_dimension[dimension["id"]]:
            weight = weights[index["strength"]]
            episode = index["episode_id"]
            if weight > 0 and (episode not in episodes or weight > episodes[episode][0]):
                episodes[episode] = (weight, index["source_refs"])

        total = sum(weight for weight, _ in episodes.values())
        score = min(total, MAX_SCORE)
        result = {
            "id": dimension["id"],
            "label": dimension["label"],
            "score": score,
            # Signal normalisé attendu par les consommateurs MCP et OSC existants.
            "appui": score / MAX_SCORE if episodes else None,
            "episode_count": len(episodes),
            "status": "documentee" if episodes else "sans_indice",
            "source_refs": list(dict.fromkeys(ref for _, refs in episodes.values() for ref in refs)),
        }
        if include_calculation:
            result["family"] = dimension.get("family", "Dimensions")
            result["definition"] = dimension["definition"]
            result["calculation"] = {
                "max_score": MAX_SCORE,
                "weights": weights,
                "total_points": total,
                "selected": [
                    {"episode_id": episode_id, "weight": weight, "source_refs": refs}
                    for episode_id, (weight, refs) in episodes.items()
                ],
            }
        dimensions.append(result)
    return dimensions


def scores_on_ten(dimensions):
    """Expose les champs utiles à la synthèse finale."""
    return [
        {
            "id": item["id"],
            "label": item["label"],
            "score": item["score"],
            "status": item["status"],
            "episode_count": item["episode_count"],
        }
        for item in dimensions
    ]
