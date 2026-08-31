import unittest
from dataclasses import replace

from novel_character_generator.chunking import build_document_chunk_manifest
from novel_character_generator.errors import ContractValidationError
from novel_character_generator.text import SourceSpan, find_occurrences, sha256_text


class TextPrimitiveTests(unittest.TestCase):
    def test_hash_preserves_raw_newlines(self) -> None:
        self.assertNotEqual(sha256_text("甲\r\n乙"), sha256_text("甲\n乙"))

    def test_span_uses_decoded_code_points(self) -> None:
        text = "甲😀乙😀"
        self.assertEqual(find_occurrences(text, "😀"), (SourceSpan(1, 2), SourceSpan(3, 4)))

    def test_occurrences_include_overlapping_matches(self) -> None:
        self.assertEqual(
            find_occurrences("aaaa", "aa"),
            (SourceSpan(0, 2), SourceSpan(1, 3), SourceSpan(2, 4)),
        )


class DocumentChunkManifestTests(unittest.TestCase):
    def test_complete_overlapping_manifest(self) -> None:
        text = "甲乙丙丁戊己庚辛壬癸"
        manifest = build_document_chunk_manifest(
            text,
            source_document_version_id="novel-v1",
            chunk_size=4,
            overlap_characters=1,
        )

        self.assertEqual(manifest.coverage_status, "complete")
        self.assertIsNone(manifest.truncation_reason)
        self.assertEqual(
            [chunk.chunk_source_span for chunk in manifest.chunks],
            [SourceSpan(0, 4), SourceSpan(3, 7), SourceSpan(6, 10)],
        )
        self.assertEqual(
            [
                (chunk.overlap_left_characters, chunk.overlap_right_characters)
                for chunk in manifest.chunks
            ],
            [(0, 1), (1, 1), (1, 0)],
        )
        manifest.validate(text)

    def test_max_chunks_is_explicitly_truncated(self) -> None:
        text = "甲乙丙丁戊己庚辛壬癸"
        manifest = build_document_chunk_manifest(
            text,
            source_document_version_id="novel-v1",
            chunk_size=4,
            overlap_characters=1,
            max_chunks=2,
        )
        self.assertEqual(manifest.coverage_status, "truncated")
        self.assertEqual(manifest.truncation_reason, "max_chunks")
        self.assertEqual(manifest.processed_source_end, 7)

    def test_max_characters_is_explicitly_truncated(self) -> None:
        text = "甲乙丙丁戊己庚辛壬癸"
        manifest = build_document_chunk_manifest(
            text,
            source_document_version_id="novel-v1",
            chunk_size=4,
            overlap_characters=1,
            max_characters=6,
        )
        self.assertEqual(manifest.coverage_status, "truncated")
        self.assertEqual(manifest.truncation_reason, "max_characters")
        self.assertEqual(manifest.processed_source_end, 6)

    def test_validation_rejects_raw_text_change(self) -> None:
        text = "甲\r\n乙"
        manifest = build_document_chunk_manifest(
            text,
            source_document_version_id="novel-v1",
            chunk_size=4,
            overlap_characters=1,
        )
        with self.assertRaisesRegex(ContractValidationError, "total_characters|document_hash"):
            manifest.validate("甲\n乙")

    def test_validation_rejects_declared_overlap_mismatch(self) -> None:
        text = "甲乙丙丁戊己"
        manifest = build_document_chunk_manifest(
            text,
            source_document_version_id="novel-v1",
            chunk_size=4,
            overlap_characters=1,
        )
        bad_first = replace(manifest.chunks[0], overlap_right_characters=0)
        broken = replace(manifest, chunks=(bad_first, *manifest.chunks[1:]))
        with self.assertRaisesRegex(ContractValidationError, "right overlap mismatch"):
            broken.validate(text)

    def test_invalid_overlap_is_rejected(self) -> None:
        with self.assertRaises(ContractValidationError):
            build_document_chunk_manifest(
                "甲乙",
                source_document_version_id="novel-v1",
                chunk_size=2,
                overlap_characters=2,
            )


if __name__ == "__main__":
    unittest.main()

