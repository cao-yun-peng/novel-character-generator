import json
import tempfile
import unittest
from pathlib import Path

from novel_character_generator.promotion_replay import replay_promotion_grounding


class PromotionReplayTests(unittest.TestCase):
    def test_saved_model_output_is_regrounded_with_partial_acceptance_without_provider(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            output = root / "output"
            source.mkdir()
            chunk_text = "青衫老者身着青衫，露出浑浊的老眼。"
            promotion_hash = "1" * 64
            envelope = {
                "schema_version": "m2-remaining-describe-promotion-envelope-v4",
                "source_document_version_id": "doc-v1",
                "chunk_id": "chunk-1",
                "describe_source_ref": {
                    "local_mention_id": "m1",
                    "packet_hash": "2" * 64,
                },
                "remaining_fragment_bindings": [
                    {
                        "fragment_ref": "d1-f1",
                        "source_evidence_quote": "青衫",
                        "source_evidence_span": {"start": 0, "end": 2},
                        "fragment_quote": "青衫",
                        "fragment_span": {"start": 0, "end": 2},
                    },
                    {
                        "fragment_ref": "d1-f2",
                        "source_evidence_quote": "青衫",
                        "source_evidence_span": {"start": 6, "end": 8},
                        "fragment_quote": "青衫",
                        "fragment_span": {"start": 6, "end": 8},
                    },
                    {
                        "fragment_ref": "d1-f3",
                        "source_evidence_quote": "浑浊的老眼",
                        "source_evidence_span": {"start": 11, "end": 16},
                        "fragment_quote": "浑浊的老眼",
                        "fragment_span": {"start": 11, "end": 16},
                    },
                ],
                "context_version": "m2-full-chunk-context-v1",
                "resolver_version": "n3-span-arbitration-v1",
                "pool_hash": "3" * 64,
                "promotion_hash": promotion_hash,
                "model_input": {
                    "describe": {
                        "mention_quote": "青衫老者",
                        "remaining_evidence_quotes": ["青衫", "浑浊的老眼"],
                    },
                    "chunk_text": chunk_text,
                },
            }
            model = {
                "chunk_index": 1,
                "chunk_id": "chunk-1",
                "describe_local_mention_id": "m1",
                "mention_quote": "青衫老者",
                "promotion_hash": promotion_hash,
                "model_output": {
                    "characters": [
                        {
                            "character_label_quote": "青衫老者",
                            "belongs_to_character": [
                                {
                                    "fact_quote": "青衫",
                                    "category": "clothing",
                                    "attribute": "衣着",
                                    "value": "青衫",
                                },
                                {
                                    "fact_quote": "浑浊的老眼",
                                    "category": "face",
                                    "attribute": "眼睛",
                                    "value": "浑浊",
                                },
                            ],
                        }
                    ]
                },
            }
            (source / "promotion-envelopes.json").write_text(
                json.dumps([envelope], ensure_ascii=False), encoding="utf-8"
            )
            (source / "promotion-model-outputs.json").write_text(
                json.dumps([model], ensure_ascii=False), encoding="utf-8"
            )
            (source / "n3-target-appearance-packets.json").write_text("[]", encoding="utf-8")

            summary = replay_promotion_grounding(source_run_dir=source, output_dir=output)

            self.assertEqual(summary["provider_calls"], 0)
            self.assertEqual(summary["promoted_characters"], 1)
            self.assertEqual(summary["promoted_grounded_facts"], 1)
            self.assertEqual(summary["promotion_grounding_issues"], 1)
            grounded = json.loads((output / "promotion-grounded-results.json").read_text("utf-8"))
            result = grounded[0]["grounded_result"]
            self.assertEqual(result["grounding_policy_version"], "promotion-partial-fact-acceptance-v1")
            facts = result["promoted_characters"][0]["grounded_belongs_to_character"]
            self.assertEqual([item["fact_quote"] for item in facts], ["浑浊的老眼"])
            self.assertIn("'青衫'", grounded[0]["grounding_issues"][0]["detail"])
            self.assertEqual(grounded[0]["grounding_issues"][0]["fact_quote"], "青衫")
            self.assertEqual(
                grounded[0]["grounding_issues"][0]["candidate_occurrence_count"],
                2,
            )
            self.assertEqual(len(result["unassigned_fragments"]), 2)


if __name__ == "__main__":
    unittest.main()
