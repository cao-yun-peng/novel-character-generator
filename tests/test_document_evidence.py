import unittest

from novel_character_generator.chunking import build_document_chunk_manifest
from novel_character_generator.document_evidence import build_document_character_evidence
from novel_character_generator.errors import ContractValidationError


def n2_packet(manifest, entry, local_id, packet_hash, label):
    return {
        "source_document_version_id": manifest.source_document_version_id,
        "chunk_id": entry.chunk_id,
        "grounded_mentions": [
            {
                "local_mention_id": local_id,
                "mention_type": "exact",
                "mention_quote": label,
                "packet_hash": packet_hash,
            }
        ],
    }


def exact_ref(manifest, entry, local_id, packet_hash):
    return {
        "source_document_version_id": manifest.source_document_version_id,
        "chunk_id": entry.chunk_id,
        "local_mention_id": local_id,
        "mention_type": "exact",
        "packet_hash": packet_hash,
    }


def fact(*, quote, evidence, fact_span, evidence_span, source_id="m1"):
    return {
        "fact_quote": quote,
        "category": "clothing",
        "attribute": "衣着颜色",
        "value": "红",
        "source_mention_id": source_id,
        "source_mention_type": "exact",
        "source_evidence_quote": evidence,
        "source_evidence_span": {"start": evidence_span[0], "end": evidence_span[1]},
        "fact_chunk_span": {"start": fact_span[0], "end": fact_span[1]},
        "match_mode": "exact",
    }


class DocumentEvidenceTests(unittest.TestCase):
    def test_overlap_fact_is_merged_and_both_chunk_sources_are_retained(self):
        text = "甲甲甲甲萧炎红衣乙乙乙乙"
        manifest = build_document_chunk_manifest(
            text,
            source_document_version_id="doc-v1",
            chunk_size=10,
            overlap_characters=6,
        )
        first, second = manifest.chunks[:2]
        hash1, hash2 = "1" * 64, "2" * 64
        n2 = [
            n2_packet(manifest, first, "m1", hash1, "萧炎"),
            n2_packet(manifest, second, "m1", hash2, "萧炎"),
        ]
        n3 = [
            {
                "target_character_ref": exact_ref(manifest, first, "m1", hash1),
                "grounded_appearance_facts": [
                    fact(quote="红衣", evidence="萧炎红衣", fact_span=(6, 8), evidence_span=(4, 8))
                ],
            },
            {
                "target_character_ref": exact_ref(manifest, second, "m1", hash2),
                "grounded_appearance_facts": [
                    fact(quote="红衣", evidence="萧炎红衣", fact_span=(2, 4), evidence_span=(0, 4))
                ],
            },
        ]

        result = build_document_character_evidence(
            document_text=text,
            manifest=manifest,
            source_n2_packets=n2,
            n3_target_packets=n3,
            promotion_grounded_results=[],
        )

        self.assertEqual(result["summary"]["input_fact_records"], 2)
        self.assertEqual(result["summary"]["document_facts"], 1)
        self.assertEqual(result["summary"]["overlap_duplicates_removed"], 1)
        item = result["appearance_facts"][0]
        self.assertEqual(item["document_fact_span"], {"start": 6, "end": 8})
        self.assertEqual(item["fact_quote"], "红衣")
        self.assertEqual(len(item["source_occurrences"]), 2)
        self.assertEqual(
            {source["chunk_id"] for source in item["source_occurrences"]},
            {first.chunk_id, second.chunk_id},
        )
        self.assertEqual(len(item["fact_hash"]), 64)

    def test_same_quote_at_different_document_spans_is_not_merged(self):
        text = "萧炎红衣，萧炎红衣"
        manifest = build_document_chunk_manifest(
            text,
            source_document_version_id="doc-v1",
            chunk_size=len(text),
            overlap_characters=0,
        )
        entry = manifest.chunks[0]
        packet_hash = "3" * 64
        result = build_document_character_evidence(
            document_text=text,
            manifest=manifest,
            source_n2_packets=[n2_packet(manifest, entry, "m1", packet_hash, "萧炎")],
            n3_target_packets=[
                {
                    "target_character_ref": exact_ref(manifest, entry, "m1", packet_hash),
                    "grounded_appearance_facts": [
                        fact(quote="红衣", evidence="萧炎红衣", fact_span=(2, 4), evidence_span=(0, 4)),
                        fact(quote="红衣", evidence="萧炎红衣", fact_span=(7, 9), evidence_span=(5, 9)),
                    ],
                }
            ],
            promotion_grounded_results=[],
        )
        self.assertEqual(result["summary"]["document_facts"], 2)
        self.assertEqual(result["summary"]["overlap_duplicates_removed"], 0)

    def test_same_quote_and_span_with_different_fact_structure_is_not_merged(self):
        text = "萧炎红衣"
        manifest = build_document_chunk_manifest(
            text,
            source_document_version_id="doc-v1",
            chunk_size=len(text),
            overlap_characters=0,
        )
        entry = manifest.chunks[0]
        packet_hash = "7" * 64
        first = fact(quote="红衣", evidence="萧炎红衣", fact_span=(2, 4), evidence_span=(0, 4))
        second = dict(first)
        second["attribute"] = "服装"
        second["value"] = "红衣"
        result = build_document_character_evidence(
            document_text=text,
            manifest=manifest,
            source_n2_packets=[n2_packet(manifest, entry, "m1", packet_hash, "萧炎")],
            n3_target_packets=[
                {
                    "target_character_ref": exact_ref(manifest, entry, "m1", packet_hash),
                    "grounded_appearance_facts": [first, second],
                }
            ],
            promotion_grounded_results=[],
        )
        self.assertEqual(result["summary"]["document_facts"], 2)
        self.assertEqual(result["summary"]["overlap_duplicates_removed"], 0)

    def test_promoted_character_fact_is_included_with_describe_origin(self):
        text = "老者身穿红衣"
        manifest = build_document_chunk_manifest(
            text,
            source_document_version_id="doc-v1",
            chunk_size=len(text),
            overlap_characters=0,
        )
        entry = manifest.chunks[0]
        promoted_ref = {
            "source_document_version_id": "doc-v1",
            "chunk_id": entry.chunk_id,
            "source_local_mention_id": "m1",
            "source_mention_type": "describe",
            "promotion_index": 1,
            "character_origin": "remaining_describe",
            "packet_hash": "4" * 64,
            "promotion_hash": "5" * 64,
        }
        promoted_fact = fact(
            quote="红衣",
            evidence="身穿红衣",
            fact_span=(4, 6),
            evidence_span=(2, 6),
        )
        promoted_fact["source_mention_type"] = "describe"
        result = build_document_character_evidence(
            document_text=text,
            manifest=manifest,
            source_n2_packets=[],
            n3_target_packets=[],
            promotion_grounded_results=[
                {
                    "grounded_result": {
                        "promoted_characters": [
                            {
                                "promoted_character_ref": promoted_ref,
                                "character_label_quote": "老者",
                                "grounded_belongs_to_character": [promoted_fact],
                            }
                        ]
                    }
                }
            ],
        )
        self.assertEqual(result["summary"]["promoted_document_facts"], 1)
        self.assertEqual(result["appearance_facts"][0]["character_origin"], "remaining_describe")

    def test_invalid_local_span_replay_is_rejected(self):
        text = "萧炎红衣"
        manifest = build_document_chunk_manifest(
            text,
            source_document_version_id="doc-v1",
            chunk_size=len(text),
            overlap_characters=0,
        )
        entry = manifest.chunks[0]
        packet_hash = "6" * 64
        with self.assertRaises(ContractValidationError):
            build_document_character_evidence(
                document_text=text,
                manifest=manifest,
                source_n2_packets=[n2_packet(manifest, entry, "m1", packet_hash, "萧炎")],
                n3_target_packets=[
                    {
                        "target_character_ref": exact_ref(manifest, entry, "m1", packet_hash),
                        "grounded_appearance_facts": [
                            fact(
                                quote="红衣",
                                evidence="萧炎红衣",
                                fact_span=(1, 3),
                                evidence_span=(0, 4),
                            )
                        ],
                    }
                ],
                promotion_grounded_results=[],
            )


if __name__ == "__main__":
    unittest.main()
