import json
import tempfile
import unittest
from collections import deque
from pathlib import Path

from novel_character_generator.chunking import build_document_chunk_manifest
from novel_character_generator.errors import ContractValidationError
from novel_character_generator.m2_batch import run_m2_from_m1_run
from novel_character_generator.n3_batch import run_n3_promotion_from_m2_run


class QueueProvider:
    cache_identity = {"provider": "test-test_n3_batch.py"}
    def __init__(self, *outputs):
        self.outputs = deque(outputs)
        self.requests = []

    def generate(self, request):
        self.requests.append(request)
        return self.outputs.popleft()


class FailIfCalledProvider:
    cache_identity = {"provider": "test-test_n3_batch.py"}
    def generate(self, request):
        raise AssertionError("resumed promotion task must not call Provider")


def write_source_m1_run(root: Path, text: str) -> None:
    manifest = build_document_chunk_manifest(
        text,
        source_document_version_id="source-v1",
        chunk_size=len(text),
        overlap_characters=0,
        chunking_policy_version="single-chunk-v1",
    )
    root.mkdir(parents=True)
    (root / "manifest.json").write_text(
        json.dumps(manifest.to_dict(), ensure_ascii=False), encoding="utf-8"
    )
    (root / "m1-model-outputs.json").write_text(
        json.dumps(
            [
                {
                    "chunk_index": 1,
                    "chunk_id": manifest.chunks[0].chunk_id,
                    "model_output": {
                        "candidate_mentions": [
                            {
                                "mention_type": "exact",
                                "mention_scope": "individual",
                                "mention_quote": "萧炎",
                                "evidence_quotes": ["萧炎黑发"],
                            },
                            {
                                "mention_type": "describe",
                                "mention_scope": "individual",
                                "mention_quote": "少女",
                                "evidence_quotes": ["少女红衣"],
                            },
                        ]
                    },
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (root / "summary.json").write_text(
        json.dumps({"schema_version": "m1-batch-summary-v2"}), encoding="utf-8"
    )


class N3PromotionBatchTests(unittest.TestCase):
    def test_runs_n3_then_promotion_and_resumes(self):
        text = "萧炎黑发。少女红衣。"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_m1 = root / "m1"
            source_m2 = root / "m2"
            output = root / "n3"
            write_source_m1_run(source_m1, text)
            run_m2_from_m1_run(
                document_text=text,
                source_run_dir=source_m1,
                provider=QueueProvider(
                    {
                        "belongs_to_target": [
                            {
                                "fact_quote": "黑发",
                                "category": "hair",
                                "attribute": "头发",
                                "value": "黑",
                            }
                        ]
                    }
                ),
                output_dir=source_m2,
            )
            provider = QueueProvider(
                {
                    "characters": [
                        {
                            "character_label_quote": "少女",
                            "belongs_to_character": [
                                {
                                    "fact_quote": "红衣",
                                    "category": "clothing",
                                    "attribute": "衣服",
                                    "value": "红",
                                }
                            ],
                        }
                    ]
                }
            )
            summary = run_n3_promotion_from_m2_run(
                document_text=text,
                source_m1_run_dir=source_m1,
                source_m2_run_dir=source_m2,
                provider=provider,
                output_dir=output,
            )

            self.assertTrue(summary["complete"])
            self.assertEqual(summary["exact_target_facts"], 1)
            self.assertEqual(summary["planned_promotion_tasks"], 1)
            self.assertEqual(summary["promoted_characters"], 1)
            self.assertEqual(summary["promoted_grounded_facts"], 1)
            self.assertFalse(summary["review_required"])
            grounded = json.loads((output / "promotion-grounded-results.json").read_text("utf-8"))
            character = grounded[0]["grounded_result"]["promoted_characters"][0]
            self.assertEqual(character["character_label_quote"], "少女")
            self.assertNotIn("character_label_span", character)
            self.assertEqual(len(provider.requests), 1)

            cached_path = next((output / "tasks").glob("*.json"))
            cached = json.loads(cached_path.read_text("utf-8"))
            cached["grounded_result"] = {"corrupt": True}
            cached["grounding_issues"] = [{"stale": True}]
            cached_path.write_text(json.dumps(cached), encoding="utf-8")
            resumed = run_n3_promotion_from_m2_run(
                document_text=text,
                source_m1_run_dir=source_m1,
                source_m2_run_dir=source_m2,
                provider=FailIfCalledProvider(),
                output_dir=output,
            )
            self.assertTrue(resumed["complete"])
            self.assertEqual(resumed["resumed_promotion_tasks"], 1)
            refreshed = json.loads(cached_path.read_text("utf-8"))
            self.assertNotIn("corrupt", refreshed["grounded_result"])
            self.assertEqual(refreshed["grounding_issues"], [])
            for invalid in (None, "changed-request"):
                with self.subTest(fingerprint=invalid):
                    refreshed["request_fingerprint"] = invalid
                    cached_path.write_text(json.dumps(refreshed), encoding="utf-8")
                    with self.assertRaisesRegex(ContractValidationError, "fingerprint"):
                        run_n3_promotion_from_m2_run(document_text=text, source_m1_run_dir=source_m1,
                            source_m2_run_dir=source_m2, provider=FailIfCalledProvider(), output_dir=output)

    def test_rejects_incomplete_source_m2_run(self):
        text = "萧炎黑发。少女红衣。"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_m1 = root / "m1"
            source_m2 = root / "m2"
            write_source_m1_run(source_m1, text)
            source_m2.mkdir()
            (source_m2 / "summary.json").write_text('{"complete": false}', encoding="utf-8")
            (source_m2 / "m2-grounded-results.json").write_text("[]", encoding="utf-8")
            with self.assertRaises(ContractValidationError):
                run_n3_promotion_from_m2_run(
                    document_text=text,
                    source_m1_run_dir=source_m1,
                    source_m2_run_dir=source_m2,
                    provider=FailIfCalledProvider(),
                    output_dir=root / "output",
                )


if __name__ == "__main__":
    unittest.main()
