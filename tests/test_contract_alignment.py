import json
import unittest
from pathlib import Path

from novel_character_generator.m1 import (
    M1_ENVELOPE_VERSION,
    M1_RESPONSE_SCHEMA,
)
from novel_character_generator.grounding import (
    EXACT_EVIDENCE_PRECEDENCE_RULE_VERSION,
    GROUNDED_PACKET_VERSION,
)
from novel_character_generator.document_evidence import (
    DOCUMENT_CHARACTER_EVIDENCE_VERSION,
    DOCUMENT_FACT_DEDUP_POLICY_VERSION,
)
from novel_character_generator.m2 import (
    M2_ATTRIBUTION_RESPONSE_SCHEMA,
    M2_CATEGORIES,
    M2_ENVELOPE_VERSION,
    M2_MODEL_FACT_SCHEMA,
    M2_PROMOTED_RESULT_VERSION,
    M2_PROMOTION_GROUNDING_POLICY_VERSION,
    M2_PROMOTION_ENVELOPE_VERSION,
    M2_PROMOTION_RESPONSE_SCHEMA,
)
from novel_character_generator.n3 import (
    N3_CHUNK_RESULT_VERSION,
    N3_POOL_RESULT_VERSION,
    N3_RESOLVER_VERSION,
    N3_TARGET_PACKET_VERSION,
)
from novel_character_generator.identity import (
    IDENTITY_CANDIDATE_POLICY_VERSION,
    IDENTITY_CONFLICT_POLICY_VERSION,
    IDENTITY_ENVELOPE_VERSION,
    IDENTITY_GROUNDED_DECISION_VERSION,
    IDENTITY_LOCAL_NODES_VERSION,
    IDENTITY_POLICY_VERSION,
    IDENTITY_REGISTRY_VERSION,
    M3_IDENTITY_RESPONSE_SCHEMA,
)


class ContractAlignmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        contract_path = (
            Path(__file__).resolve().parents[1]
            / "docs"
            / "contracts"
            / "simplified-character-evidence-v3-model-schemas.json"
        )
        cls.schema = json.loads(contract_path.read_text(encoding="utf-8"))

    def test_m1_envelope_version_matches_machine_contract(self) -> None:
        envelope = self.schema["$defs"]["M1OrchestrationEnvelope"]
        self.assertEqual(envelope["properties"]["schema_version"]["const"], M1_ENVELOPE_VERSION)
        self.assertEqual(
            set(envelope["required"]),
            {
                "schema_version",
                "source_document_version_id",
                "chunking_policy_version",
                "chunk_id",
                "chunk_hash",
                "chunk_source_span",
                "model_input",
            },
        )

    def test_model_input_contains_only_chunk_text(self) -> None:
        model_input = self.schema["$defs"]["M1MentionDiscoveryInput"]
        self.assertFalse(model_input["additionalProperties"])
        self.assertEqual(model_input["required"], ["chunk_text"])
        self.assertEqual(set(model_input["properties"]), {"chunk_text"})

    def test_runtime_response_schema_matches_contract_fields(self) -> None:
        contract_output = self.schema["$defs"]["M1MentionDiscoveryResult"]
        self.assertFalse(M1_RESPONSE_SCHEMA["additionalProperties"])
        self.assertEqual(M1_RESPONSE_SCHEMA["required"], contract_output["required"])
        runtime_item = M1_RESPONSE_SCHEMA["properties"]["candidate_mentions"]["items"]
        contract_item = contract_output["properties"]["candidate_mentions"]["items"]
        self.assertFalse(runtime_item["additionalProperties"])
        self.assertEqual(set(runtime_item["required"]), set(contract_item["required"]))
        self.assertEqual(set(runtime_item["properties"]), set(contract_item["properties"]))

    def test_grounded_contract_removes_mention_locations_and_adds_scope(self) -> None:
        packet = self.schema["$defs"]["N2GroundedMentionPacket"]
        self.assertEqual(packet["properties"]["schema_version"]["const"], GROUNDED_PACKET_VERSION)
        self.assertEqual(
            packet["properties"]["evidence_precedence_policy_version"]["const"],
            EXACT_EVIDENCE_PRECEDENCE_RULE_VERSION,
        )
        mention = packet["properties"]["grounded_mentions"]["items"]
        self.assertIn("mention_scope", mention["properties"])
        self.assertNotIn("mention_occurrence_count", mention["properties"])
        self.assertNotIn("mention_source_spans", mention["properties"])
        self.assertNotIn("mention_quote_hash", mention["properties"])
        approved = self.schema["$defs"]["N2ApprovedEvidence"]
        self.assertIn("match_mode", approved["required"])
        self.assertNotIn("quote_hash", approved["properties"])

    def test_document_evidence_contract_versions_match_runtime(self) -> None:
        packet = self.schema["$defs"]["DocumentCharacterEvidence"]
        self.assertEqual(packet["properties"]["schema_version"]["const"], DOCUMENT_CHARACTER_EVIDENCE_VERSION)
        self.assertEqual(
            packet["properties"]["dedup_policy_version"]["const"],
            DOCUMENT_FACT_DEDUP_POLICY_VERSION,
        )

    def test_m2_model_contract_is_fact_only_and_contains_no_orchestration_fields(self) -> None:
        self.assertEqual(self.schema["version"], "3.12.0-draft1")
        defs = self.schema["$defs"]
        model_input = defs["M2CandidateAppearanceParsingInput"]
        model_output = defs["M2CandidateAppearanceParsingResult"]
        model_fact = defs["M2ModelBelongsToFact"]

        target = model_input["properties"]["target"]
        describe = model_input["properties"]["describe_blocks"]["items"]
        self.assertEqual(
            set(target["properties"]),
            {"mention_quote", "approved_evidence_quotes"},
        )
        self.assertEqual(
            set(describe["properties"]),
            {"mention_quote", "evidence_quotes"},
        )
        self.assertEqual(set(model_output["properties"]), {"belongs_to_target"})
        self.assertEqual(
            set(model_fact["properties"]),
            {"fact_quote", "category", "attribute", "value"},
        )

        forbidden = {
            "describe_ref",
            "fragment_ref",
            "evidence_ref",
            "assessments",
            "attribution_status",
            "claimed_evidence_quote",
            "claimed_span",
            "support_quote",
            "support_span",
            "epistemic_status",
        }
        serialized = json.dumps(
            {
                "input": model_input,
                "output": model_output,
                "fact": model_fact,
            },
            ensure_ascii=False,
        )
        for field in forbidden:
            self.assertNotIn(f'"{field}"', serialized)

    def test_m2_refs_and_spans_remain_code_only(self) -> None:
        envelope = self.schema["$defs"]["M2OrchestrationEnvelope"]
        self.assertEqual(
            envelope["properties"]["schema_version"]["const"],
            "m2-orchestration-envelope-v4",
        )
        self.assertIn("target_evidence_bindings", envelope["properties"])
        self.assertIn("describe_source_bindings", envelope["properties"])
        self.assertIn("task_cache_key", envelope["properties"])
        self.assertEqual(
            envelope["properties"]["model_input"]["$ref"],
            "#/$defs/M2CandidateAppearanceParsingInput",
        )
        grounded = self.schema["$defs"]["M2GroundedCandidateAppearanceParsingResult"]
        self.assertEqual(
            set(grounded["properties"]),
            {"target_character_ref", "task_cache_key", "grounded_belongs_to_target"},
        )
        grounded_fact = self.schema["$defs"]["M2GroundedBelongsToFact"]
        self.assertIn("source_evidence_span", grounded_fact["properties"])
        self.assertIn("fact_chunk_span", grounded_fact["properties"])
        self.assertNotIn("attribution_status", grounded_fact["properties"])
        self.assertNotIn("assessments", grounded["properties"])

    def test_m2_promotion_model_contract_also_hides_refs_and_spans(self) -> None:
        defs = self.schema["$defs"]
        model_input = defs["M2RemainingDescribePromotionInput"]
        model_output = defs["M2RemainingDescribePromotionResult"]
        describe = model_input["properties"]["describe"]
        character = model_output["properties"]["characters"]["items"]

        self.assertEqual(
            set(describe["properties"]),
            {"mention_quote", "remaining_evidence_quotes"},
        )
        self.assertEqual(
            set(character["properties"]),
            {"character_label_quote", "belongs_to_character"},
        )
        serialized = json.dumps(
            {"input": model_input, "output": model_output},
            ensure_ascii=False,
        )
        for field in ("fragment_ref", "claimed_span", "support_span", "epistemic_status"):
            self.assertNotIn(f'"{field}"', serialized)

    def test_m2_runtime_schemas_and_versions_match_machine_contract(self) -> None:
        defs = self.schema["$defs"]
        self.assertEqual(
            defs["M2OrchestrationEnvelope"]["properties"]["schema_version"]["const"],
            M2_ENVELOPE_VERSION,
        )
        self.assertEqual(
            defs["M2RemainingDescribePromotionEnvelope"]["properties"]["schema_version"]["const"],
            M2_PROMOTION_ENVELOPE_VERSION,
        )
        self.assertEqual(
            defs["M2GroundedPromotedDescribeCharactersResult"]["properties"]["schema_version"]["const"],
            M2_PROMOTED_RESULT_VERSION,
        )
        self.assertEqual(
            defs["M2GroundedPromotedDescribeCharactersResult"]["properties"]["grounding_policy_version"]["const"],
            M2_PROMOTION_GROUNDING_POLICY_VERSION,
        )
        self.assertEqual(
            set(M2_MODEL_FACT_SCHEMA["properties"]),
            set(defs["M2ModelBelongsToFact"]["properties"]),
        )
        self.assertEqual(
            set(M2_MODEL_FACT_SCHEMA["properties"]["category"]["enum"]),
            set(M2_CATEGORIES),
        )
        self.assertEqual(
            set(M2_ATTRIBUTION_RESPONSE_SCHEMA["properties"]),
            set(defs["M2CandidateAppearanceParsingResult"]["properties"]),
        )
        self.assertEqual(
            set(M2_PROMOTION_RESPONSE_SCHEMA["properties"]),
            set(defs["M2RemainingDescribePromotionResult"]["properties"]),
        )

    def test_grounded_promotion_contract_uses_minimal_hydrated_facts(self) -> None:
        grounded = self.schema["$defs"]["M2GroundedPromotedDescribeCharactersResult"]
        character = grounded["properties"]["promoted_characters"]["items"]
        self.assertEqual(
            set(character["properties"]),
            {
                "promoted_character_ref",
                "character_label_quote",
                "grounded_belongs_to_character",
            },
        )
        self.assertEqual(
            character["properties"]["grounded_belongs_to_character"]["items"]["$ref"],
            "#/$defs/M2GroundedBelongsToFact",
        )

    def test_n3_runtime_contract_versions_and_minimal_facts_align(self) -> None:
        defs = self.schema["$defs"]
        self.assertEqual(
            defs["N3ChunkResolutionResult"]["properties"]["schema_version"]["const"],
            N3_CHUNK_RESULT_VERSION,
        )
        self.assertEqual(
            defs["N3ValidatedAppearancePacket"]["properties"]["schema_version"]["const"],
            N3_TARGET_PACKET_VERSION,
        )
        self.assertEqual(
            defs["N3DescribePoolResolutionResult"]["properties"]["schema_version"]["const"],
            N3_POOL_RESULT_VERSION,
        )
        self.assertEqual(
            defs["N3DescribePoolResolutionResult"]["properties"]["resolver_version"]["const"],
            N3_RESOLVER_VERSION,
        )
        facts = defs["N3ValidatedAppearancePacket"]["properties"]["grounded_appearance_facts"]
        self.assertEqual(facts["items"]["$ref"], "#/$defs/M2GroundedBelongsToFact")

    def test_m3_model_boundary_and_code_contracts_align(self) -> None:
        defs = self.schema["$defs"]
        model_input = defs["M3CharacterIdentityInput"]
        model_output = defs["M3CharacterIdentityResult"]
        self.assertFalse(model_input["additionalProperties"])
        self.assertEqual(
            set(model_input["properties"]),
            {"current_character", "candidate_character", "bridge_context_quotes"},
        )
        self.assertFalse(model_output["additionalProperties"])
        self.assertEqual(
            set(model_output["properties"]),
            {"identity_relation", "label_relation", "identity_evidence_quotes"},
        )
        self.assertEqual(
            set(M3_IDENTITY_RESPONSE_SCHEMA["properties"]),
            set(model_output["properties"]),
        )
        serialized = json.dumps(model_input, ensure_ascii=False)
        for forbidden in ("node_key", "character_id", "span", "hash", "ref", "cache"):
            self.assertNotIn(f'"{forbidden}"', serialized)

        self.assertEqual(
            defs["DocumentLocalCharacterNodes"]["properties"]["schema_version"]["const"],
            IDENTITY_LOCAL_NODES_VERSION,
        )
        self.assertEqual(
            defs["M3IdentityEnvelope"]["properties"]["schema_version"]["const"],
            IDENTITY_ENVELOPE_VERSION,
        )
        self.assertEqual(
            defs["GroundedIdentityDecision"]["properties"]["schema_version"]["const"],
            IDENTITY_GROUNDED_DECISION_VERSION,
        )
        registry = defs["DocumentCharacterRegistry"]["properties"]
        self.assertEqual(registry["schema_version"]["const"], IDENTITY_REGISTRY_VERSION)
        self.assertEqual(registry["identity_policy_version"]["const"], IDENTITY_POLICY_VERSION)
        self.assertEqual(
            registry["candidate_policy_version"]["const"],
            IDENTITY_CANDIDATE_POLICY_VERSION,
        )
        self.assertEqual(
            registry["conflict_policy_version"]["const"],
            IDENTITY_CONFLICT_POLICY_VERSION,
        )


if __name__ == "__main__":
    unittest.main()
