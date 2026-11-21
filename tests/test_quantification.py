import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.quantification import load_catalog, quantify_dimensions


class QuantificationTests(unittest.TestCase):
    def test_catalog_lists_the_creative_session_traits(self):
        catalog = load_catalog()
        self.assertEqual(catalog.version, 4)
        self.assertEqual({item["id"] for item in catalog.dimensions}, {
            "enthousiasme", "reveur", "passionne", "creativite", "bienveillance",
            "force_de_proposition", "impulsivite", "autocritique", "domination",
            "extraversion", "introversion", "confiance_en_soi",
            "manque_de_confiance_en_soi", "analytique", "humour", "angoisse",
        })
        self.assertEqual(
            [item["id"] for item in catalog.dimensions if item.get("family") == "Bonus"],
            ["force_de_proposition"],
        )

    def test_scores_advance_once_per_episode_and_cap_at_ten(self):
        catalog = load_catalog()

        def index(episode, strength, ref, **extra):
            return {"dimension_id": "confiance_en_soi", "episode_id": episode,
                    "strength": strength, "source_refs": [ref], **extra}

        indices = [
            index("first", "indirect", "t1:o1"),
            index("first", "direct", "t2:o1"),
            index("second", "indirect", "t3:o1"),
            index("third", "direct", "t4:o1", relation="contre_indice"),
            index("fourth", "direct", "t5:o1"),
            index("fifth", "direct", "t6:o1"),
        ]
        for count, expected in enumerate((0, 2, 4, 6, 6, 10, 10)):
            results = quantify_dimensions(indices[:count], catalog)
            confidence = next(item for item in results if item["id"] == "confiance_en_soi")
            self.assertEqual(confidence["score"], expected)
        self.assertEqual(confidence["episode_count"], 4)
        self.assertEqual(confidence["source_refs"], ["t2:o1", "t3:o1", "t5:o1", "t6:o1"])
        self.assertNotIn("contre_appui", confidence)
        other = next(item for item in results if item["id"] == "manque_de_confiance_en_soi")
        self.assertEqual(other["score"], 0)
        self.assertEqual(other["status"], "sans_indice")

    def test_new_dimension_and_override_from_yaml(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / "catalog.yaml"
            path.write_text("""
version: 19
quantification: {weights: {direct: 4, indirect: 2}}
dimensions:
  - id: curiosite
    label: Curiosité
    definition: Décrit une recherche d'explications nouvelles.
    quantification: {weights: {direct: 3}}
""", encoding="utf-8")
            catalog = load_catalog(path)
        result, = quantify_dimensions([{
            "dimension_id": "curiosite", "episode_id": "ep1", "relation": "appui",
            "strength": "direct", "source_refs": ["t1:o1"],
        }], catalog)
        self.assertEqual(catalog.version, 19)
        self.assertEqual(result["score"], 3)
