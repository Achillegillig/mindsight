import json
import unittest

from haystack import component
from haystack.dataclasses import ChatMessage

from app.extraction import ExtractionError, extract_turn
from app.quantification import load_catalog


@component
class FakeGenerator:
    def __init__(self, response, prompts):
        self.response = response
        self.prompts = prompts

    @component.output_types(replies=list[ChatMessage])
    def run(self, messages: list[ChatMessage]):
        self.prompts.append(json.loads(messages[-1].text))
        return {"replies": [ChatMessage.from_assistant(self.response)]}


def observe(quote, **fields):
    return {
        "label": "Proposition", "quote": quote, "kind": "action", "subject": "participant",
        "mode": "vecu", **fields,
    }


def link(**fields):
    return {
        "dimension_id": "confiance_en_soi", "reading": "La personne exprime sa confiance dans sa capacité à porter le projet.",
        "observation_ids": ["o1"], "strength": "direct",
        "episode_ref": "new:projet", "episode_label": "Projet collectif", **fields,
    }


class ExtractionTests(unittest.TestCase):
    def setUp(self):
        self.catalog = load_catalog()
        self.prompts = []

    def analyze(self, answer, *responses):
        replies = iter(responses)

        def factory(**kwargs):
            return FakeGenerator(next(replies), self.prompts)

        return extract_turn("test", "fake", "Une question absente du récit ?", answer,
                            catalog=self.catalog, include_trace=True, generator_factory=factory)

    def test_two_passes_anchor_and_validate_links(self):
        answer = "Un galet. Je me sentais capable de porter le projet. Mon ami était inquiet."
        result = self.analyze(
            answer,
            json.dumps({"observations": [
                observe("Je me sentais capable de porter le projet"),
                observe("Un galet", kind="image", mode="fiction"),
                observe("Mon ami était inquiet", kind="ressenti", subject="tiers"),
                observe("Une question absente du récit"),
                observe("galet", kind=[]),
            ]}),
            json.dumps({"dimensions": [
                link(), link(observation_ids=["o7"]), link(dimension_id="inconnue"),
                link(observation_ids=["o2"]), link(relation="contre_indice"),
            ]}),
        )
        self.assertEqual(len(self.prompts), 2)
        self.assertNotIn("catalog", self.prompts[0])
        self.assertEqual(len(self.prompts[1]["observations"]), 3)
        self.assertEqual(result["expressed_feelings"], [])
        self.assertEqual(result["visual_elements"][0]["quote"], "Un galet")
        self.assertEqual(len(result["dimensions"]), 1)
        self.assertEqual(result["trace"], {"observation_candidates": 5, "interpretation_candidates": 5})
        item = result["observations"][0]
        self.assertEqual(answer[item["start"]:item["end"]], item["quote"])

    def test_fiction_counts_for_narrative_traits_without_inferring_a_personal_trait(self):
        answer = "Un pigeon commenterait chaque miette comme une finale."
        result = self.analyze(
            answer,
            json.dumps({"observations": [
                observe(answer, mode="fiction"),
                {"label": "Pigeon", "quote": "Un pigeon", "kind": "action",
                 "mode": "fiction", "subject": "personnage"},
            ]}),
            json.dumps({"dimensions": [
                link(dimension_id="humour"),
                link(dimension_id="extraversion"),
                link(dimension_id="creativite", observation_ids=["o2"]),
            ]}),
        )
        self.assertEqual(
            [(item["dimension_id"], item["strength"]) for item in result["dimensions"]],
            [("humour", "indirect")],
        )

    def test_empty_observations_skip_model_and_keep_empty_dimensions(self):
        result = self.analyze("oui, oui", json.dumps({"observations": [observe("oui"), observe("Oui", kind="")]}))
        self.assertEqual(result["dimensions"], [])
        self.assertEqual(len(self.prompts), 1)

    def test_failures_distinguish_missing_observations_and_partial_extraction(self):
        answer = "J’ai peur."
        with self.assertRaises(ExtractionError):
            self.analyze(answer, "non JSON")
        result = self.analyze(answer, json.dumps({"observations": [observe(answer, kind="ressenti")]}), "non JSON")
        self.assertEqual(result["expressed_feelings"][0]["quote"], answer)
        self.assertIsNone(result["dimensions"])
