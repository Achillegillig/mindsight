import unittest
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory

from app.quantification import load_catalog, quantify_dimensions


class QuantificationTests(unittest.TestCase):
    def test_catalog_covers_four_families_and_distinguishes_sensitivities(self):
        catalog = load_catalog()
        groups = Counter(item["family"] for item in catalog.dimensions)
        self.assertEqual(groups, {
            "Personnalité apparente": 4, "Fonctionnement intellectuel": 5,
            "Fonctionnement émotionnel": 4, "Fonctionnement relationnel": 4,
        })
        ids = {item["id"] for item in catalog.dimensions}
        self.assertTrue({"sensibilite_apparente", "sensibilite_emotionnelle"} <= ids)

    def test_weights_count_episodes_and_keep_counter_evidence(self):
        catalog = load_catalog()

        def index(episode, strength, ref, relation="appui"):
            return {"dimension_id": "affirmation_de_soi", "episode_id": episode,
                    "strength": strength, "source_refs": [ref], "relation": relation}

        items = quantify_dimensions([
            index("first", "direct", "t1:o1"),
            index("first", "indirect", "t2:o1"),
            index("second", "indirect", "t3:o1"),
            index("third", "direct", "t4:o1", "contre_indice"),
        ], catalog)
        output = {item["id"]: item for item in items}
        initiative = output["affirmation_de_soi"]
        self.assertEqual(initiative["appui"], 0.6)
        self.assertEqual(initiative["contre_appui"], 0.5)
        self.assertEqual(initiative["episode_count"], 3)
        self.assertEqual(initiative["source_refs"], ["t1:o1", "t3:o1", "t4:o1"])
        self.assertEqual(initiative["status"], "nuance")
        self.assertIsNone(output["empathie"]["appui"])

    def test_new_dimension_and_override_from_yaml(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / "catalog.yaml"
            path.write_text("""
version: 19
quantification: {weights: {direct: 1, indirect: 0.5}, saturation: 1}
dimensions:
  - id: curiosite
    label: Curiosité
    definition: Décrit une recherche d'explications nouvelles.
    quantification: {saturation: 3}
""", encoding="utf-8")
            catalog = load_catalog(path)
        result, = quantify_dimensions([{
            "dimension_id": "curiosite", "episode_id": "ep1", "relation": "appui",
            "strength": "direct", "source_refs": ["t1:o1"],
        }], catalog)
        self.assertEqual(catalog.version, 19)
        self.assertEqual(result["appui"], 0.25)
        self.assertEqual(result["contre_appui"], 0)
