import json
import tempfile
import unittest
from collections import deque
from pathlib import Path

from novel_character_generator.chunking import build_document_chunk_manifest
from novel_character_generator.errors import ContractValidationError
from novel_character_generator.m2_batch import run_m2_from_m1_run


class QueueProvider:
    cache_identity = {"provider": "test-m2-fixture-v1"}
    def __init__(self, *outputs):
        self.outputs = deque(outputs)
        self.requests = []

    def generate(self, request):
        self.requests.append(request)
        return self.outputs.popleft()


class FailIfCalledProvider:
    cache_identity = {"provider": "test-m2-fixture-v1"}
    def generate(self, request):
        raise AssertionError("resumed M2 task must not call Provider")


def model_fact(quote, category, attribute, value):
    return {
        "fact_quote": quote,
        "category": category,
        "attribute": attribute,
        "value": value,
    }


def write_source_run(root: Path, text: str) -> None:
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
    candidates = [
        {
            "mention_type": "exact",
            "mention_scope": "individual",
            "mention_quote": "萧熏儿",
            "evidence_quotes": ["萧熏儿睫毛修长"],
        },
        {
            "mention_type": "describe",
            "mention_scope": "individual",
            "mention_quote": "少女",
            "evidence_quotes": ["少女眼睛美丽"],
        },
        {
            "mention_type": "exact",
            "mention_scope": "individual",
            "mention_quote": "萧炎",
            "evidence_quotes": ["萧炎身形瘦削"],
        },
    ]
    (root / "m1-model-outputs.json").write_text(
        json.dumps(
            [
                {
                    "chunk_index": 1,
                    "chunk_id": manifest.chunks[0].chunk_id,
                    "chunk_source_span": manifest.chunks[0].chunk_source_span.to_dict(),
                    "model_output": {"candidate_mentions": candidates},
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (root / "summary.json").write_text(
        json.dumps({"schema_version": "m1-batch-summary-v2"}), encoding="utf-8"
    )


class M2BatchTests(unittest.TestCase):
    def test_replays_n2_runs_all_exact_tasks_and_writes_separate_outputs(self):
        text = "萧熏儿睫毛修长。少女眼睛美丽。萧炎身形瘦削。"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            output = root / "output"
            write_source_run(source, text)
            provider = QueueProvider(
                {"belongs_to_target": [model_fact("眼睛美丽", "face", "眼睛", "美丽")]},
                {"belongs_to_target": [model_fact("身形瘦削", "body", "身形", "瘦削")]},
            )

            summary = run_m2_from_m1_run(
                document_text=text,
                source_run_dir=source,
                provider=provider,
                output_dir=output,
            )

            self.assertTrue(summary["complete"])
            self.assertEqual(summary["planned_tasks"], 2)
            self.assertEqual(summary["grounded_facts"], 2)
            self.assertEqual(summary["grounded_facts_by_source_type"], {"exact": 1, "describe": 1})
            self.assertEqual(len(provider.requests), 2)
            self.assertTrue((output / "source-n2-grounded-packets.json").exists())
            self.assertTrue((output / "m2-model-outputs.json").exists())
            self.assertTrue((output / "m2-grounded-results.json").exists())
            self.assertTrue((output / "run-history.json").exists())
            self.assertEqual(json.loads((output / "failures.json").read_text("utf-8")), [])

            model_outputs = json.loads((output / "m2-model-outputs.json").read_text("utf-8"))
            grounded_results = json.loads((output / "m2-grounded-results.json").read_text("utf-8"))
            self.assertEqual(len(model_outputs), 2)
            self.assertEqual(len(grounded_results), 2)
            self.assertNotIn("fact_chunk_span", json.dumps(model_outputs, ensure_ascii=False))
            self.assertIn("fact_chunk_span", json.dumps(grounded_results, ensure_ascii=False))

            resumed = run_m2_from_m1_run(
                document_text=text,
                source_run_dir=source,
                provider=FailIfCalledProvider(),
                output_dir=output,
            )
            self.assertTrue(resumed["complete"])
            self.assertEqual(resumed["resumed_tasks"], 2)
            history = json.loads((output / "run-history.json").read_text("utf-8"))
            self.assertEqual(len(history), 2)
            self.assertEqual(history[0]["new_provider_calls"], 0)
            self.assertEqual(history[1]["resumed_tasks"], 2)

    def test_source_document_mismatch_fails_before_provider(self):
        text = "萧熏儿睫毛修长。少女眼睛美丽。萧炎身形瘦削。"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            write_source_run(source, text)
            with self.assertRaises(ContractValidationError):
                run_m2_from_m1_run(
                    document_text=text + "新增字符",
                    source_run_dir=source,
                    provider=FailIfCalledProvider(),
                    output_dir=root / "output",
                )


if __name__ == "__main__":
    unittest.main()
