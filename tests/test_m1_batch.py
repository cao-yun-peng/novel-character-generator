import json
import tempfile
import unittest
from pathlib import Path

from novel_character_generator.errors import ProviderResponseError
from novel_character_generator.errors import ContractValidationError
from novel_character_generator.m1_batch import run_m1_document


class EchoEvidenceProvider:
    def __init__(self, fail_on_call: int | None = None) -> None:
        self.calls = 0
        self.fail_on_call = fail_on_call

    def generate(self, request):
        self.calls += 1
        if self.calls == self.fail_on_call:
            raise ProviderResponseError("synthetic safe failure")
        text = request.user_payload["chunk_text"]
        return {
            "candidate_mentions": [
                {
                    "mention_type": None,
                    "mention_scope": None,
                    "mention_quote": None,
                    "evidence_quotes": [text[:2]],
                }
            ]
        }


class ExactDescribeDuplicateProvider:
    def generate(self, request):
        return {
            "candidate_mentions": [
                {
                    "mention_type": "exact",
                    "mention_scope": "individual",
                    "mention_quote": "萧熏儿",
                    "evidence_quotes": ["微笑的小脸"],
                },
                {
                    "mention_type": "describe",
                    "mention_scope": "individual",
                    "mention_quote": "少女",
                    "evidence_quotes": ["微笑的小脸"],
                },
            ]
        }


class M1BatchTests(unittest.TestCase):
    def test_batch_serializes_n2_exact_precedence_trace_and_summary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            summary = run_m1_document(
                document_text="萧熏儿与少女都有微笑的小脸。",
                provider=ExactDescribeDuplicateProvider(),
                output_dir=output,
                chunk_size=100,
                overlap_characters=0,
            )
            packets = json.loads((output / "m1-grounded-packets.json").read_text("utf-8"))
            traces = json.loads((output / "n2-grounding-traces.json").read_text("utf-8"))

            self.assertEqual(summary["schema_version"], "m1-batch-summary-v3")
            self.assertEqual(summary["exact_evidence_precedence"]["shadowed_describe_evidence"], 1)
            self.assertEqual(summary["exact_evidence_precedence"]["removed_empty_describe_blocks"], 1)
            self.assertEqual([item["mention_quote"] for item in packets[0]["grounded_mentions"]], ["萧熏儿"])
            self.assertEqual(
                [event["code"] for event in traces[0]["trace_events"][-2:]],
                ["describe_evidence_shadowed_by_exact", "describe_removed_after_exact_dedup"],
            )

    def test_writes_complete_resumable_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            provider = EchoEvidenceProvider()
            first = run_m1_document(
                document_text="甲乙丙丁戊己庚辛壬癸",
                provider=provider,
                output_dir=output,
                chunk_size=6,
                overlap_characters=2,
            )
            self.assertTrue(first["complete"])
            self.assertEqual(first["planned_chunks"], 2)
            self.assertEqual(provider.calls, 2)
            self.assertTrue((output / "manifest.json").exists())
            self.assertTrue((output / "m1-model-outputs.json").exists())
            self.assertTrue((output / "n2-grounding-traces.json").exists())
            self.assertEqual(len(json.loads((output / "m1-grounded-packets.json").read_text("utf-8"))), 2)
            self.assertEqual(first["exact_evidence_precedence"]["shadowed_describe_evidence"], 0)
            self.assertEqual(first["exact_evidence_precedence"]["removed_empty_describe_blocks"], 0)

            second_provider = EchoEvidenceProvider()
            second = run_m1_document(
                document_text="甲乙丙丁戊己庚辛壬癸",
                provider=second_provider,
                output_dir=output,
                chunk_size=6,
                overlap_characters=2,
            )
            self.assertTrue(second["complete"])
            self.assertEqual(second["resumed_chunks"], 2)
            self.assertEqual(second["new_provider_calls"], 0)
            self.assertEqual(second_provider.calls, 0)

    def test_records_failure_and_returns_incomplete(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            summary = run_m1_document(
                document_text="甲乙丙丁戊己庚辛壬癸",
                provider=EchoEvidenceProvider(fail_on_call=2),
                output_dir=output,
                chunk_size=6,
                overlap_characters=2,
            )
            failures = json.loads((output / "failures.json").read_text("utf-8"))
            self.assertFalse(summary["complete"])
            self.assertEqual(summary["succeeded_chunks"], 1)
            self.assertEqual(summary["failed_chunks"], 1)
            self.assertEqual(failures[0]["error_type"], "ProviderResponseError")
            self.assertNotIn("甲乙", json.dumps(failures, ensure_ascii=False))

    def test_refuses_to_resume_legacy_chunk_contract(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            run_m1_document(
                document_text="甲乙丙丁",
                provider=EchoEvidenceProvider(),
                output_dir=output,
                chunk_size=4,
                overlap_characters=0,
            )
            chunk_path = next((output / "chunks").glob("*.json"))
            saved = json.loads(chunk_path.read_text("utf-8"))
            saved["schema_version"] = "m1-chunk-result-v1"
            chunk_path.write_text(json.dumps(saved, ensure_ascii=False), encoding="utf-8")

            with self.assertRaisesRegex(ContractValidationError, "use a new output directory"):
                run_m1_document(
                    document_text="甲乙丙丁",
                    provider=EchoEvidenceProvider(),
                    output_dir=output,
                    chunk_size=4,
                    overlap_characters=0,
                )


if __name__ == "__main__":
    unittest.main()
