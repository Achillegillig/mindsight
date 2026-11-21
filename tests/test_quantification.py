import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.quantification import load_catalog, quantify_dimensions


class QuantificationTests(unittest.TestCase):
    def test_catalog_lists_the_creative_session_traits(self):
        catalog = load_catalog()
        self.assertEqual(catalog.version, 5)
        self.assertEqual([item["id"] for item in catalog.dimensions], [
            "analytique", "enthousiasme", "extraversion", "humour", "torture",
            "reveur", "creativite",
        ])

    def test_distinct_evidence_changes_scores_without_rewarding_repetition(self):
        catalog = load_catalog()

        def index(episode, intensity, ref, **extra):
            return {"dimension_id": "analytique", "episode_id": episode, "intensity": intensity,
                    "strength": "direct", "source_refs": [ref], **extra}

        indices = [
            index("first", "leger", "t1:o1"),
            index("first", "frappant", "t2:o1"),
            index("second", "leger", "t3:o1"),
            index("third", "frappant", "t4:o1", relation="contre_indice"),
            index("fourth", "net", "t5:o1"),
            index("fifth", "frappant", "t6:o1"),
        ]
        for count, expected in enumerate((0, 2, 8, 8, 8, 9, 10)):
            result, *_ = quantify_dimensions(indices[:count], catalog)
            self.assertEqual(result["score"], expected)
        self.assertEqual(result["episode_count"], 4)
        self.assertEqual(result["source_refs"], ["t2:o1", "t3:o1", "t5:o1", "t6:o1"])
        for intensity, expected in (("leger", 4), ("net", 8)):
            result, *others = quantify_dimensions([
                index(f"episode-{i}", intensity, f"t{i}:o1") for i in range(1, 10)
            ], catalog)
            self.assertEqual(result["score"], expected)
            self.assertTrue(all(item["score"] == 0 and item["appui"] is None for item in others))

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
