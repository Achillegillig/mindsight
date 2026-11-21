"""Catalogue éditable et calcul déterministe des signaux de rendu."""

from collections import defaultdict
from dataclasses import dataclass
from math import isfinite
from pathlib import Path
import re

import yaml

CATALOG_PATH = Path(__file__).with_name("dimensions.yaml")


@dataclass(frozen=True)
class Catalog:
    version: int
    dimensions: tuple[dict, ...]
    weights: dict[str, float]
    saturation: float


def number(value, *, positive=False):
    if type(value) not in (int, float) or not isfinite(value) or value < 0 or (positive and value == 0):
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
        minimum = item.get("min_observations", 1)
        if type(minimum) is not int or minimum < 1:
            raise ValueError("min_observations doit être un entier positif.")
        overrides = item.get("quantification", {})
        if not isinstance(overrides, dict):
            raise ValueError("Les réglages par dimension doivent former un objet.")
        number(overrides.get("saturation", rules.get("saturation")), positive=True)
        overrides_weights = overrides.get("weights", {})
        if not isinstance(overrides_weights, dict) or not overrides_weights.keys() <= weights.keys():
            raise ValueError("Poids par dimension inconnus.")
        for value in overrides_weights.values():
            number(value)

    return Catalog(
        data["version"], tuple(dimensions),
        {name: number(value) for name, value in weights.items()},
        number(rules.get("saturation"), positive=True),
    )


def quantify_dimensions(indices, catalog, *, include_calculation=False):
    """Un seul poids maximal par épisode, dimension et sens."""
    by_dimension = defaultdict(list)
    for index in indices:
        by_dimension[index["dimension_id"]].append(index)
    dimensions = []
    for dimension in catalog.dimensions:
        settings = dimension.get("quantification", {})
        weights = {**catalog.weights, **settings.get("weights", {})}
        k = settings.get("saturation", catalog.saturation)
        episodes = {"appui": {}, "contre_indice": {}}
        for index in by_dimension[dimension["id"]]:
            weight = weights[index["strength"]]
            evidence = episodes[index["relation"]]
            key = index["episode_id"]
            if weight > 0 and (key not in evidence or weight > evidence[key][0]):
                evidence[key] = (weight, index["source_refs"])

        support, counter = episodes.values()
        total_support = sum(weight for weight, _ in support.values())
        total_counter = sum(weight for weight, _ in counter.values())
        observed = bool(support or counter)
        result = {
            "id": dimension["id"],
            "label": dimension["label"],
            "appui": total_support / (total_support + k) if observed else None,
            "contre_appui": total_counter / (total_counter + k) if observed else None,
            "episode_count": len(support.keys() | counter.keys()),
            "status": "nuance" if support and counter else "documentee" if observed else "sans_indice",
            "source_refs": list(dict.fromkeys(
                ref for group in episodes.values() for _, refs in group.values() for ref in refs
            )),
        }
        if include_calculation:
            result["family"] = dimension.get("family", "Dimensions")
            result["definition"] = dimension["definition"]
            result["calculation"] = {
                "k": k,
                "weights": weights,
                "support_total": total_support,
                "counter_total": total_counter,
                "selected": [
                    {"relation": relation, "episode_id": episode_id, "weight": weight, "source_refs": refs}
                    for relation, group in episodes.items()
                    for episode_id, (weight, refs) in group.items()
                ],
            }
        dimensions.append(result)
    return dimensions
