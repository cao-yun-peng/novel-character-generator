from __future__ import annotations

import hashlib
import json

from novel_character_generator.application.ports.field_disambiguation import (
    FIELD_DISAMBIGUATION_ARTIFACT_SCHEMA_VERSION,
    FIELD_DISAMBIGUATION_CONTRACT_VERSION,
    FIELD_DISAMBIGUATION_PROMPT_VERSION,
    FieldDisambiguationArtifactCounts,
    FieldDisambiguationDecisionArtifact,
    FieldDisambiguationExecutionRequest,
    FieldDisambiguationProvider,
    FieldDisambiguationResult,
)
from novel_character_generator.application.ports.local_grounding import GroundedLocalPacket
from novel_character_generator.domain.policies.visual_field_catalog import (
    VISUAL_FIELD_CATALOG_VERSION,
    is_catalog_field,
)


class FieldDisambiguationContractError(ValueError):
    """An M2 response failed deterministic source or catalog validation."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _canonical_hash(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def validate_field_disambiguation_output(
    packet: GroundedLocalPacket,
    output: FieldDisambiguationResult,
) -> FieldDisambiguationResult:
    """Validate deterministic coverage, provenance, catalog, and grouping invariants."""

    if output.chunk_id != packet.chunk_id:
        raise FieldDisambiguationContractError("field_disambiguation_chunk_id_mismatch")
    if output.field_registry_version != VISUAL_FIELD_CATALOG_VERSION:
        raise FieldDisambiguationContractError("field_disambiguation_catalog_version_mismatch")

    facts_by_id = {item.fact_id: item for item in packet.grounded_facts}
    expected_decision_ids = [item.fact_id for item in packet.grounded_facts]
    decision_ids = [item.fact_id for item in output.decisions]
    if len(decision_ids) != len(set(decision_ids)):
        raise FieldDisambiguationContractError("duplicate_field_disambiguation_fact")
    if set(decision_ids) != set(facts_by_id):
        raise FieldDisambiguationContractError("incomplete_field_disambiguation_coverage")
    if decision_ids != expected_decision_ids:
        raise FieldDisambiguationContractError("field_disambiguation_decision_order_mismatch")

    for decision in output.decisions:
        fact = facts_by_id[decision.fact_id]
        if decision.evidence_quote != fact.evidence_quote:
            raise FieldDisambiguationContractError(
                "field_disambiguation_evidence_quote_mismatch"
            )
        mapping_ids = [item.mapping_id for item in decision.mappings]
        if mapping_ids != [f"m{index}" for index in range(1, len(mapping_ids) + 1)]:
            raise FieldDisambiguationContractError("invalid_materialized_mapping_ids")
        semantic_ids = list(dict.fromkeys(item.semantic_unit_id for item in decision.mappings))
        if semantic_ids != [f"s{index}" for index in range(1, len(semantic_ids) + 1)]:
            raise FieldDisambiguationContractError("invalid_materialized_semantic_unit_ids")

        semantic_bindings: dict[str, tuple[str, str | None]] = {}
        dimensions: set[tuple[str, str]] = set()
        for mapping in decision.mappings:
            if not is_catalog_field(mapping.field_path):
                raise FieldDisambiguationContractError(
                    f"field_not_in_frozen_catalog:{mapping.field_path}"
                )
            if not mapping.normalized_value.strip():
                raise FieldDisambiguationContractError("blank_normalized_value")
            if mapping.evidence_quote != fact.evidence_quote:
                raise FieldDisambiguationContractError(
                    "field_disambiguation_mapping_evidence_mismatch"
                )
            if mapping.referent_quote is None:
                if mapping.referent_kind != "whole_character":
                    raise FieldDisambiguationContractError(
                        "null_referent_requires_whole_character"
                    )
            elif (
                mapping.referent_quote not in fact.evidence_quote
                and mapping.referent_quote not in fact.local_context.text
            ):
                raise FieldDisambiguationContractError(
                    "field_disambiguation_referent_not_in_source"
                )

            binding = (mapping.referent_kind, mapping.referent_quote)
            prior_binding = semantic_bindings.setdefault(mapping.semantic_unit_id, binding)
            if prior_binding != binding:
                raise FieldDisambiguationContractError(
                    "semantic_unit_has_conflicting_referent"
                )
            dimension = (mapping.semantic_unit_id, mapping.field_path)
            if dimension in dimensions:
                raise FieldDisambiguationContractError("duplicate_semantic_unit_dimension")
            dimensions.add(dimension)
    return output


class FieldDisambiguationShadowService:
    """Runs M2 without persistence, identity resolution, scope resolution, or promotion."""

    def __init__(self, provider: FieldDisambiguationProvider) -> None:
        self.provider = provider

    async def run(
        self, request: FieldDisambiguationExecutionRequest
    ) -> FieldDisambiguationDecisionArtifact:
        packet = request.grounded_packet
        if not packet.grounded_facts:
            raise FieldDisambiguationContractError("m2_requires_grounded_facts")
        detailed = await self.provider.disambiguate_detailed(packet)
        output = validate_field_disambiguation_output(packet, detailed.output)

        mapped_facts = sum(item.decision == "map" for item in output.decisions)
        deferred_facts = sum(item.decision == "defer" for item in output.decisions)
        rejected_facts = sum(item.decision == "reject" for item in output.decisions)
        mapping_count = sum(len(item.mappings) for item in output.decisions)
        reason_codes: list[str] = []
        if deferred_facts:
            reason_codes.append("deferred_facts_present")
        if rejected_facts:
            reason_codes.append("rejected_facts_present")

        input_fingerprint = _canonical_hash(
            {
                "contract_version": FIELD_DISAMBIGUATION_CONTRACT_VERSION,
                "field_registry_version": VISUAL_FIELD_CATALOG_VERSION,
                "prompt_version": self.provider.prompt_version,
                "prompt_hash": self.provider.prompt_hash,
                "model_config_version": self.provider.model_config_version,
                "data_policy_version": request.data_policy_version,
                "grounded_packet": packet.model_dump(mode="json"),
            }
        )
        output_fingerprint = _canonical_hash(output.model_dump(mode="json"))
        return FieldDisambiguationDecisionArtifact(
            schema_version=FIELD_DISAMBIGUATION_ARTIFACT_SCHEMA_VERSION,
            node_id="M2",
            run_id=packet.run_id,
            source_document_version_id=packet.source_document_version_id,
            chunk_id=packet.chunk_id,
            evaluation_attempt_id=request.evaluation_attempt_id,
            contract_version=FIELD_DISAMBIGUATION_CONTRACT_VERSION,
            field_registry_version=VISUAL_FIELD_CATALOG_VERSION,
            prompt_version=FIELD_DISAMBIGUATION_PROMPT_VERSION,
            prompt_hash=self.provider.prompt_hash,
            model_config_version=self.provider.model_config_version,
            data_policy_version=request.data_policy_version,
            input_fingerprint=input_fingerprint,
            output_fingerprint=output_fingerprint,
            status="completed_with_warnings" if reason_codes else "succeeded",
            reason_codes=tuple(reason_codes),
            counts=FieldDisambiguationArtifactCounts(
                input_facts=len(packet.grounded_facts),
                mapped_facts=mapped_facts,
                deferred_facts=deferred_facts,
                rejected_facts=rejected_facts,
                mappings=mapping_count,
            ),
            usage=detailed.metadata,
            output=output,
        )
