from __future__ import annotations

import hashlib
import json

from novel_character_generator.application.ports.local_observation import (
    LOCAL_OBSERVATION_ARTIFACT_SCHEMA_VERSION,
    LOCAL_OBSERVATION_CONTRACT_VERSION,
    LOCAL_OBSERVATION_PROMPT_VERSION,
    LocalObservationArtifactCounts,
    LocalObservationDecisionArtifact,
    LocalObservationDiscoveryInput,
    LocalObservationDiscoveryResult,
    LocalObservationExecutionRequest,
    LocalObservationProvider,
)


class LocalObservationContractError(ValueError):
    """A model response failed deterministic M1 contract validation."""

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


def _normalized_text(value: str) -> str:
    return " ".join(value.split()).casefold()


def validate_local_observation_output(
    request: LocalObservationDiscoveryInput,
    output: LocalObservationDiscoveryResult,
) -> LocalObservationDiscoveryResult:
    """Validate only deterministic source and graph invariants.

    This function deliberately does not decide whether a proposition is visual,
    select a canonical field, infer identity, or repair missing model facts.
    """

    if output.chunk_id != request.chunk_id:
        raise LocalObservationContractError("local_observation_chunk_id_mismatch")

    allowed_families = set(request.allowed_coarse_families)
    invalid_families = sorted(
        {fact.coarse_family for fact in output.facts} - allowed_families
    )
    if invalid_families:
        raise LocalObservationContractError(
            f"local_observation_family_not_allowed:{','.join(invalid_families)}"
        )

    quotes: list[tuple[str, str]] = []
    quotes.extend(("entity", item.mention_quote) for item in output.entities)
    quotes.extend(("fact", item.evidence_quote) for item in output.facts)
    quotes.extend(("temporal_signal", item.evidence_quote) for item in output.temporal_signals)
    quotes.extend(("unresolved", item.evidence_quote) for item in output.unresolved_items)
    for kind, quote in quotes:
        if quote not in request.chunk_text:
            raise LocalObservationContractError(
                f"local_observation_quote_not_in_chunk:{kind}"
            )

    referenced_entities = {fact.entity_ref for fact in output.facts}
    referenced_entities.update(
        signal.entity_ref for signal in output.temporal_signals if signal.entity_ref is not None
    )
    referenced_entities.update(
        item.entity_ref for item in output.unresolved_items if item.entity_ref is not None
    )
    unused_entities = sorted(
        entity.local_entity_id
        for entity in output.entities
        if entity.local_entity_id not in referenced_entities
    )
    if unused_entities:
        raise LocalObservationContractError(
            f"local_observation_unused_entity:{','.join(unused_entities)}"
        )

    seen_facts: set[tuple[str, str, str, str, str]] = set()
    fact_unresolved_keys: set[tuple[str | None, str, str]] = set()
    for fact in output.facts:
        key = (
            fact.entity_ref,
            _normalized_text(fact.evidence_quote),
            _normalized_text(fact.raw_proposition),
            fact.coarse_family,
            fact.epistemic_status,
        )
        if key in seen_facts:
            raise LocalObservationContractError("duplicate_local_observation_fact")
        seen_facts.add(key)
        fact_unresolved_keys.add(key[:3])

    seen_unresolved: set[tuple[str | None, str, str, str]] = set()
    for item in output.unresolved_items:
        shared_key = (
            item.entity_ref,
            _normalized_text(item.evidence_quote),
            _normalized_text(item.raw_proposition),
        )
        unresolved_key = (*shared_key, item.reason_code)
        if unresolved_key in seen_unresolved:
            raise LocalObservationContractError("duplicate_local_observation_unresolved")
        seen_unresolved.add(unresolved_key)
        if shared_key in fact_unresolved_keys:
            raise LocalObservationContractError(
                "local_observation_asserted_unresolved_double_write"
            )
    return output


class LocalObservationShadowService:
    """Runs M1 and returns an immutable artifact without persistence side effects."""

    def __init__(self, provider: LocalObservationProvider) -> None:
        self.provider = provider

    async def run(
        self, request: LocalObservationExecutionRequest
    ) -> LocalObservationDecisionArtifact:
        detailed = await self.provider.discover_detailed(request.payload)
        output = validate_local_observation_output(request.payload, detailed.output)
        reason_codes: list[str] = []
        if not (
            output.entities
            or output.facts
            or output.temporal_signals
            or output.unresolved_items
        ):
            reason_codes.append("empty_discovery")
        if output.unresolved_items:
            reason_codes.append("unresolved_items_present")

        input_fingerprint = _canonical_hash(
            {
                "contract_version": LOCAL_OBSERVATION_CONTRACT_VERSION,
                "prompt_version": self.provider.prompt_version,
                "prompt_hash": self.provider.prompt_hash,
                "model_config_version": self.provider.model_config_version,
                "data_policy_version": request.data_policy_version,
                "payload": request.payload.model_dump(mode="json"),
            }
        )
        output_fingerprint = _canonical_hash(output.model_dump(mode="json"))
        counts = LocalObservationArtifactCounts(
            entities=len(output.entities),
            facts=len(output.facts),
            temporal_signals=len(output.temporal_signals),
            unresolved_items=len(output.unresolved_items),
        )
        return LocalObservationDecisionArtifact(
            schema_version=LOCAL_OBSERVATION_ARTIFACT_SCHEMA_VERSION,
            node_id="M1",
            run_id=request.run_id,
            source_document_version_id=request.source_document_version_id,
            chunk_id=request.payload.chunk_id,
            evaluation_attempt_id=request.evaluation_attempt_id,
            contract_version=LOCAL_OBSERVATION_CONTRACT_VERSION,
            prompt_version=LOCAL_OBSERVATION_PROMPT_VERSION,
            prompt_hash=self.provider.prompt_hash,
            model_config_version=self.provider.model_config_version,
            data_policy_version=request.data_policy_version,
            input_fingerprint=input_fingerprint,
            output_fingerprint=output_fingerprint,
            status="completed_with_warnings" if reason_codes else "succeeded",
            reason_codes=tuple(reason_codes),
            counts=counts,
            usage=detailed.metadata,
            output=output,
        )
