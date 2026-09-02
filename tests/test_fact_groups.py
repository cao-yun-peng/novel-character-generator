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
from novel_character_generator.document_profiles import build_document_character_profiles
from novel_character_generator.errors import ContractValidationError
from novel_character_generator.fact_groups import (
    CANONICAL_FACT_GROUPING_REASON,
    DOCUMENT_CHARACTER_FACT_GROUPS_VERSION,
    POST_LINK_FACT_GROUPING_POLICY_VERSION,
    build_document_character_fact_groups,
    run_document_fact_group_assembly,
)
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


def _local_ref(local_id):
    return {
        "source_document_version_id": "doc-v1",
        "chunk_id": "chunk-1",
        "local_mention_id": local_id,
        "mention_type": "exact",
        "packet_hash": local_id[-1] * 64,
    }


def _wrapped_ref(local_id):
    return {"ref_type": "local", "local_character_ref": _local_ref(local_id)}


def _fact(text, *, label, local_id, attribute="衣着", assigned=True):
    span = {"start": 2, "end": 4} if assigned else {"start": 7, "end": 9}
    quote = "红衣" if assigned else "白发"
    evidence_span = {"start": 0, "end": 4} if assigned else {"start": 5, "end": 9}
    evidence_quote = "少年红衣" if assigned else "老者白发"
    value = "红衣" if assigned else "白发"
    hash_input = {
        "source_document_version_id": "doc-v1",
        "character_origin": "exact",
        "character_label_quote": label,
        "fact_quote": quote,
        "document_fact_span": span,
        "category": "clothing" if assigned else "hair",
        "attribute": attribute,
        "value": value,
        "dedup_policy_version": DOCUMENT_FACT_DEDUP_POLICY_VERSION,
    }
    return {
        "fact_hash": _canonical_hash(hash_input),
        "character_origin": "exact",
        "character_label_quote": label,
        "fact_quote": quote,
        "category": "clothing" if assigned else "hair",
        "attribute": attribute,
        "value": value,
        "document_fact_span": span,
        "source_occurrences": [
            {
                "chunk_id": "chunk-1",
                "chunk_hash": sha256_text(text),
                "chunk_source_span": {"start": 0, "end": len(text)},
                "source_character_ref": _local_ref(local_id),
                "source_mention_id": local_id,
                "source_mention_type": "exact",
                "source_evidence_quote": evidence_quote,
                "chunk_evidence_span": evidence_span,
                "document_evidence_span": evidence_span,
                "chunk_fact_span": span,
                "match_mode": "exact",
            }
        ],
    }


def _inputs():
    text = "少年红衣。老者白发。"
    first = _fact(text, label="少年", local_id="m1")
    duplicate = _fact(text, label="萧炎", local_id="m2")
    other_attribute = _fact(text, label="少年", local_id="m3", attribute="颜色")
    unassigned = _fact(text, label="老者", local_id="m4", assigned=False)
    character_id = "char-" + "1" * 20
    zero_fact_id = "char-" + "2" * 20
    registry = {
        "schema_version": IDENTITY_REGISTRY_VERSION,
        "identity_policy_version": IDENTITY_POLICY_VERSION,
        "candidate_policy_version": IDENTITY_CANDIDATE_POLICY_VERSION,
        "conflict_policy_version": IDENTITY_CONFLICT_POLICY_VERSION,
        "source_document_version_id": "doc-v1",
        "document_hash": sha256_text(text),
        "characters": [
            {
                "character_id": character_id,
                "identity_status": "linked",
                "canonical_label": "萧炎",
                "canonical_label_status": "confirmed_name_like",
                "labels": [{"label_quote": "萧炎", "label_role": "name", "globally_unique": True}],
                "member_character_refs": [_wrapped_ref("m1"), _wrapped_ref("m2"), _wrapped_ref("m3")],
                "appearance_fact_refs": [
                    {"fact_hash": fact["fact_hash"], "fact_quote": fact["fact_quote"]}
                    for fact in (first, duplicate, other_attribute)
                ],
                "possible_conflicts": [],
            },
            {
                "character_id": zero_fact_id,
                "identity_status": "singleton",
                "canonical_label": "路人",
                "canonical_label_status": "provisional_description",
                "labels": [{"label_quote": "路人", "label_role": "contextual_description", "globally_unique": False}],
                "member_character_refs": [_wrapped_ref("m4")],
                "appearance_fact_refs": [],
                "possible_conflicts": [],
            },
        ],
        "unresolved_bindings": [],
        "review_items": [],
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
        "appearance_facts": [first, duplicate, other_attribute, unassigned],
        "summary": {},
    }
    profiles = build_document_character_profiles(
        document_text=text,
        registry=registry,
        evidence=evidence,
    )
    return text, registry, profiles


class FactGroupsTests(unittest.TestCase):
    def test_groups_only_exact_structural_duplicates_and_preserves_provenance(self):
        text, registry, profiles = _inputs()
        result = build_document_character_fact_groups(
            document_text=text,
            registry=registry,
            profiles=profiles,
        )
        self.assertEqual(result["schema_version"], DOCUMENT_CHARACTER_FACT_GROUPS_VERSION)
        self.assertEqual(result["grouping_policy_version"], POST_LINK_FACT_GROUPING_POLICY_VERSION)
        self.assertEqual(result["summary"]["raw_appearance_facts"], 4)
        self.assertEqual(result["summary"]["assigned_raw_appearance_facts"], 3)
        self.assertEqual(result["summary"]["canonical_fact_groups"], 2)
        self.assertEqual(result["summary"]["collapsed_raw_fact_members"], 1)
        self.assertEqual(result["summary"]["source_occurrences"], 4)
        merged = next(group for group in result["fact_groups"] if group["attribute"] == "衣着")
        self.assertEqual(merged["grouping_reason"], CANONICAL_FACT_GROUPING_REASON)
        self.assertEqual(len(merged["source_fact_hashes"]), 2)
        self.assertEqual(len(merged["source_occurrences"]), 2)
        self.assertEqual(
            {item["source_fact_hash"] for item in merged["source_occurrences"]},
            set(merged["source_fact_hashes"]),
        )
        self.assertEqual(len(result["unassigned_source_fact_hashes"]), 1)
        self.assertEqual(len(result["unassigned_source_occurrences"]), 1)
        self.assertEqual(
            result["unassigned_source_occurrences"][0]["source_fact_hash"],
            result["unassigned_source_fact_hashes"][0],
        )
        zero = next(item for item in result["characters"] if item["canonical_label"] == "路人")
        self.assertEqual(zero["canonical_fact_ids"], [])

    def test_canonical_ids_do_not_depend_on_raw_fact_order(self):
        text, registry, profiles = _inputs()
        first = build_document_character_fact_groups(
            document_text=text,
            registry=registry,
            profiles=profiles,
        )
        profiles["characters"][0]["appearance_facts"].reverse()
        second = build_document_character_fact_groups(
            document_text=text,
            registry=registry,
            profiles=profiles,
        )
        self.assertEqual(
            [item["canonical_fact_id"] for item in first["fact_groups"]],
            [item["canonical_fact_id"] for item in second["fact_groups"]],
        )

    def test_registry_profile_document_or_fact_set_mismatch_is_rejected(self):
        text, registry, profiles = _inputs()
        profiles["source_document_version_id"] = "other"
        with self.assertRaises(ContractValidationError):
            build_document_character_fact_groups(document_text=text, registry=registry, profiles=profiles)

        text, registry, profiles = _inputs()
        registry["characters"][0]["appearance_fact_refs"].pop()
        with self.assertRaises(ContractValidationError):
            build_document_character_fact_groups(document_text=text, registry=registry, profiles=profiles)

    def test_tampered_raw_fact_and_summary_are_rejected(self):
        text, registry, profiles = _inputs()
        profiles["characters"][0]["appearance_facts"][0]["value"] = "蓝衣"
        with self.assertRaises(ContractValidationError):
            build_document_character_fact_groups(document_text=text, registry=registry, profiles=profiles)

        text, registry, profiles = _inputs()
        profiles["summary"]["source_occurrences"] = 99
        with self.assertRaises(ContractValidationError):
            build_document_character_fact_groups(document_text=text, registry=registry, profiles=profiles)

    def test_run_writes_artifact_hashes_and_rejects_wrong_registry_source(self):
        text, registry, profiles = _inputs()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry_file = root / "registry.json"
            profiles_file = root / "profiles.json"
            output_file = root / "groups" / "document-character-fact-groups.json"
            registry_file.write_text(json.dumps(registry, ensure_ascii=False), encoding="utf-8")
            registry_hash = sha256(registry_file.read_bytes()).hexdigest()
            profiles["source_artifacts"]["character_registry"] = {
                "path": str(registry_file),
                "hash": registry_hash,
            }
            profiles_file.write_text(json.dumps(profiles, ensure_ascii=False), encoding="utf-8")
            summary = run_document_fact_group_assembly(
                document_text=text,
                registry_file=registry_file,
                profiles_file=profiles_file,
                output_file=output_file,
            )
            result = json.loads(output_file.read_text(encoding="utf-8"))
            self.assertEqual(summary, result["summary"])
            self.assertEqual(result["source_artifacts"]["character_registry"]["hash"], registry_hash)

            profiles["source_artifacts"]["character_registry"]["hash"] = "f" * 64
            profiles_file.write_text(json.dumps(profiles, ensure_ascii=False), encoding="utf-8")
            with self.assertRaises(ContractValidationError):
                run_document_fact_group_assembly(
                    document_text=text,
                    registry_file=registry_file,
                    profiles_file=profiles_file,
                    output_file=output_file,
                )


if __name__ == "__main__":
    unittest.main()
