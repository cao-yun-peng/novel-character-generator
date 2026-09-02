import copy
import json
import tempfile
import unittest
from hashlib import sha256
from pathlib import Path

from novel_character_generator.document_evidence import (
    DOCUMENT_CHARACTER_EVIDENCE_VERSION,
    DOCUMENT_FACT_DEDUP_POLICY_VERSION,
)
from novel_character_generator.document_profiles import (
    DOCUMENT_CHARACTER_PROFILES_VERSION,
    DOCUMENT_PROFILE_JOIN_POLICY_VERSION,
    build_document_character_profiles,
    run_document_profile_assembly,
)
from novel_character_generator.errors import ContractValidationError
from novel_character_generator.identity import (
    IDENTITY_CANDIDATE_POLICY_VERSION,
    IDENTITY_CONFLICT_POLICY_VERSION,
    IDENTITY_POLICY_VERSION,
    IDENTITY_REGISTRY_VERSION,
)
from novel_character_generator.text import sha256_text


def _canonical_hash(value):
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(payload.encode("utf-8")).hexdigest()


def _local_ref(local_id="m1"):
    return {
        "source_document_version_id": "doc-v1",
        "chunk_id": "chunk-1",
        "local_mention_id": local_id,
        "mention_type": "exact",
        "packet_hash": local_id[-1] * 64,
    }


def _wrapped_ref(local_id="m1"):
    return {"ref_type": "local", "local_character_ref": _local_ref(local_id)}


def _fact(text, *, quote, fact_span, evidence_quote, evidence_span, label="萧炎", local_id="m1"):
    document_fact_span = {"start": fact_span[0], "end": fact_span[1]}
    hash_input = {
        "source_document_version_id": "doc-v1",
        "character_origin": "exact",
        "character_label_quote": label,
        "fact_quote": quote,
        "document_fact_span": document_fact_span,
        "category": "clothing",
        "attribute": "衣着",
        "value": quote,
        "dedup_policy_version": DOCUMENT_FACT_DEDUP_POLICY_VERSION,
    }
    return {
        "fact_hash": _canonical_hash(hash_input),
        "character_origin": "exact",
        "character_label_quote": label,
        "fact_quote": quote,
        "category": "clothing",
        "attribute": "衣着",
        "value": quote,
        "document_fact_span": document_fact_span,
        "source_occurrences": [
            {
                "chunk_id": "chunk-1",
                "chunk_hash": sha256_text(text),
                "chunk_source_span": {"start": 0, "end": len(text)},
                "source_character_ref": _local_ref(local_id),
                "source_mention_id": local_id,
                "source_mention_type": "exact",
                "source_evidence_quote": evidence_quote,
                "chunk_evidence_span": {"start": evidence_span[0], "end": evidence_span[1]},
                "document_evidence_span": {"start": evidence_span[0], "end": evidence_span[1]},
                "chunk_fact_span": document_fact_span,
                "match_mode": "exact",
            }
        ],
    }


def _character(character_id, label, member_id, facts, *, conflicts=None):
    return {
        "character_id": character_id,
        "identity_status": "singleton",
        "canonical_label": label,
        "canonical_label_status": "confirmed_name_like",
        "labels": [{"label_quote": label, "label_role": "name", "globally_unique": True}],
        "member_character_refs": [_wrapped_ref(member_id)],
        "appearance_fact_refs": [
            {"fact_hash": fact["fact_hash"], "fact_quote": fact["fact_quote"]} for fact in facts
        ],
        "possible_conflicts": conflicts or [],
    }


def _inputs():
    text = "萧炎红衣。老者白发。"
    first = _fact(
        text,
        quote="红衣",
        fact_span=(2, 4),
        evidence_quote="萧炎红衣",
        evidence_span=(0, 4),
    )
    second = _fact(
        text,
        quote="白发",
        fact_span=(7, 9),
        evidence_quote="老者白发",
        evidence_span=(5, 9),
        label="老者",
        local_id="m2",
    )
    registry = {
        "schema_version": IDENTITY_REGISTRY_VERSION,
        "identity_policy_version": IDENTITY_POLICY_VERSION,
        "candidate_policy_version": IDENTITY_CANDIDATE_POLICY_VERSION,
        "conflict_policy_version": IDENTITY_CONFLICT_POLICY_VERSION,
        "source_document_version_id": "doc-v1",
        "document_hash": sha256_text(text),
        "characters": [
            _character("char-" + "1" * 20, "萧炎", "m1", [first]),
            _character("char-" + "2" * 20, "老者", "m2", []),
        ],
        "unresolved_bindings": [],
        "review_items": [
            {
                "review_item_id": "review-1",
                "review_type": "identity_review",
                "subject_character_ref": _wrapped_ref("m1"),
                "label_quote": "萧炎",
                "candidate_character_ids": ["char-" + "2" * 20],
                "grounded_identity_evidence": [],
                "issue_codes": ["uncertain"],
                "status": "pending",
            }
        ],
        "cannot_link_constraints": [],
        "summary": {},
    }
    evidence = {
        "schema_version": DOCUMENT_CHARACTER_EVIDENCE_VERSION,
        "dedup_policy_version": DOCUMENT_FACT_DEDUP_POLICY_VERSION,
        "source_document_version_id": "doc-v1",
        "document_hash": sha256_text(text),
        "coverage_status": "complete",
        "processed_source_end": len(text),
        "source_artifacts": {},
        "source_chunks": [],
        "appearance_facts": [first, second],
        "summary": {},
    }
    return text, registry, evidence


class DocumentProfilesTests(unittest.TestCase):
    def test_accepts_registry_from_supported_v1_candidate_retrieval(self):
        text, registry, evidence = _inputs()
        registry["candidate_policy_version"] = "bounded-local-candidate-retrieval-v1"
        result = build_document_character_profiles(
            document_text=text,
            registry=registry,
            evidence=evidence,
        )
        self.assertEqual(
            result["candidate_policy_version"],
            "bounded-local-candidate-retrieval-v1",
        )

    def test_materializes_facts_preserves_zero_fact_character_and_unassigned_fact(self):
        text, registry, evidence = _inputs()
        result = build_document_character_profiles(
            document_text=text,
            registry=registry,
            evidence=evidence,
        )

        self.assertEqual(result["schema_version"], DOCUMENT_CHARACTER_PROFILES_VERSION)
        self.assertEqual(result["join_policy_version"], DOCUMENT_PROFILE_JOIN_POLICY_VERSION)
        self.assertEqual(result["summary"]["global_characters"], 2)
        self.assertEqual(result["summary"]["assigned_appearance_facts"], 1)
        self.assertEqual(result["summary"]["unassigned_appearance_facts"], 1)
        first, second = result["characters"]
        self.assertEqual(first["appearance_facts"][0]["fact_quote"], "红衣")
        self.assertEqual(second["appearance_facts"], [])
        self.assertEqual(first["review_item_ids"], ["review-1"])
        self.assertEqual(second["review_item_ids"], ["review-1"])
        self.assertEqual(result["unassigned_appearance_facts"][0]["fact_quote"], "白发")

    def test_document_identity_mismatch_is_rejected(self):
        text, registry, evidence = _inputs()
        evidence["source_document_version_id"] = "another-document"
        with self.assertRaises(ContractValidationError):
            build_document_character_profiles(document_text=text, registry=registry, evidence=evidence)

    def test_missing_registry_fact_is_rejected(self):
        text, registry, evidence = _inputs()
        registry["characters"][0]["appearance_fact_refs"][0]["fact_hash"] = "f" * 64
        with self.assertRaises(ContractValidationError):
            build_document_character_profiles(document_text=text, registry=registry, evidence=evidence)

    def test_duplicate_evidence_fact_hash_is_rejected(self):
        text, registry, evidence = _inputs()
        evidence["appearance_facts"].append(copy.deepcopy(evidence["appearance_facts"][0]))
        with self.assertRaises(ContractValidationError):
            build_document_character_profiles(document_text=text, registry=registry, evidence=evidence)

    def test_registry_fact_quote_mismatch_is_rejected(self):
        text, registry, evidence = _inputs()
        registry["characters"][0]["appearance_fact_refs"][0]["fact_quote"] = "蓝衣"
        with self.assertRaises(ContractValidationError):
            build_document_character_profiles(document_text=text, registry=registry, evidence=evidence)

    def test_fact_span_replay_failure_is_rejected(self):
        text, registry, evidence = _inputs()
        evidence["appearance_facts"][0]["document_fact_span"] = {"start": 1, "end": 3}
        with self.assertRaises(ContractValidationError):
            build_document_character_profiles(document_text=text, registry=registry, evidence=evidence)

    def test_conflict_may_only_reference_its_character_facts(self):
        text, registry, evidence = _inputs()
        registry["characters"][0]["possible_conflicts"] = [
            {"conflict_id": "c1", "fact_hashes": [evidence["appearance_facts"][1]["fact_hash"]]}
        ]
        with self.assertRaises(ContractValidationError):
            build_document_character_profiles(document_text=text, registry=registry, evidence=evidence)

    def test_run_writes_output_and_file_artifact_hashes(self):
        text, registry, evidence = _inputs()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry_file = root / "registry.json"
            evidence_file = root / "evidence.json"
            output_file = root / "profiles" / "document-character-profiles.json"
            registry_file.write_text(json.dumps(registry, ensure_ascii=False), encoding="utf-8")
            evidence_file.write_text(json.dumps(evidence, ensure_ascii=False), encoding="utf-8")

            summary = run_document_profile_assembly(
                document_text=text,
                registry_file=registry_file,
                evidence_file=evidence_file,
                output_file=output_file,
            )

            self.assertTrue(output_file.exists())
            result = json.loads(output_file.read_text(encoding="utf-8"))
            self.assertEqual(summary, result["summary"])
            self.assertEqual(
                result["source_artifacts"]["character_registry"]["hash"],
                sha256(registry_file.read_bytes()).hexdigest(),
            )


if __name__ == "__main__":
    unittest.main()
