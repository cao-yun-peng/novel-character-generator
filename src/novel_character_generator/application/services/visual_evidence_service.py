from __future__ import annotations

import hashlib
import json

from novel_character_generator.application.ports.model_provider import ModelCallMetadata
from novel_character_generator.application.ports.visual_evidence import (
    VISUAL_EVIDENCE_ARTIFACT_SCHEMA_VERSION,
    VISUAL_EVIDENCE_CONTRACT_VERSION,
    VISUAL_EVIDENCE_PROMPT_VERSION,
    VISUAL_EVIDENCE_SOURCE_MATCH_POLICY_VERSION,
    DetailedVisualEvidenceResult,
    VisualEvidenceArtifactCounts,
    VisualEvidenceDecisionArtifact,
    VisualEvidenceDiscoveryResult,
    VisualEvidenceExecutionRequest,
    VisualEvidenceProvider,
)


class VisualEvidenceContractError(ValueError):
    def __init__(
        self,
        code: str,
        *,
        output: VisualEvidenceDiscoveryResult | None = None,
        metadata: ModelCallMetadata | None = None,
        input_fingerprint: str | None = None,
        output_fingerprint: str | None = None,
    ) -> None:
        super().__init__(code)
        self.code = code
        self.output = output
        self.metadata = metadata
        self.input_fingerprint = input_fingerprint
        self.output_fingerprint = output_fingerprint


def _canonical_hash(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _non_whitespace_view(value: str) -> tuple[str, tuple[int, ...]]:
    characters: list[str] = []
    source_positions: list[int] = []
    for index, character in enumerate(value):
        if character.isspace():
            continue
        characters.append(character)
        source_positions.append(index)
    return "".join(characters), tuple(source_positions)


def _unique_source_slice(chunk_text: str, quote: str) -> str:
    normalized_chunk, source_positions = _non_whitespace_view(chunk_text)
    normalized_quote, _ = _non_whitespace_view(quote)
    if not normalized_quote:
        raise VisualEvidenceContractError("visual_evidence_quote_not_in_chunk")

    starts: list[int] = []
    search_from = 0
    while True:
        start = normalized_chunk.find(normalized_quote, search_from)
        if start < 0:
            break
        starts.append(start)
        search_from = start + 1
    if not starts:
        raise VisualEvidenceContractError("visual_evidence_quote_not_in_chunk")
    if len(starts) != 1:
        raise VisualEvidenceContractError("visual_evidence_quote_not_unique_in_chunk")

    start = starts[0]
    raw_start = source_positions[start]
    raw_end = source_positions[start + len(normalized_quote) - 1] + 1
    return chunk_text[raw_start:raw_end]


def validate_visual_evidence_output(
    chunk_text: str,
    output: VisualEvidenceDiscoveryResult,
    *,
    expected_chunk_id: str | None = None,
) -> VisualEvidenceDiscoveryResult:
    """Validate source-boundary invariants without interpreting visual semantics."""

    if expected_chunk_id is not None and output.chunk_id != expected_chunk_id:
        raise VisualEvidenceContractError("visual_evidence_chunk_id_mismatch")

    for mention in output.mentions:
        if mention.mention_quote not in chunk_text:
            raise VisualEvidenceContractError("visual_evidence_quote_not_in_chunk")

    canonical_candidates = tuple(
        candidate.model_copy(
            update={
                "evidence_quote": _unique_source_slice(
                    chunk_text,
                    candidate.evidence_quote,
                )
            }
        )
        for candidate in output.evidence_candidates
    )
    canonical_output = output.model_copy(
        update={"evidence_candidates": canonical_candidates}
    )

    seen_candidates: set[tuple[str | None, str]] = set()
    for candidate in canonical_output.evidence_candidates:
        key = (
            candidate.local_owner_id,
            "".join(candidate.evidence_quote.split()).casefold(),
        )
        if key in seen_candidates:
            raise VisualEvidenceContractError("duplicate_visual_evidence_candidate")
        seen_candidates.add(key)
    return canonical_output


class VisualEvidenceShadowService:
    """Run M1 v2 without persistence, semantic classification, or promotion authority."""

    def __init__(self, provider: VisualEvidenceProvider) -> None:
        self.provider = provider

    async def run(
        self, request: VisualEvidenceExecutionRequest
    ) -> VisualEvidenceDecisionArtifact:
        detailed: DetailedVisualEvidenceResult = await self.provider.discover_detailed(
            request.payload
        )
        input_fingerprint = _canonical_hash(
            {
                "contract_version": VISUAL_EVIDENCE_CONTRACT_VERSION,
                "prompt_version": self.provider.prompt_version,
                "prompt_hash": self.provider.prompt_hash,
                "model_config_version": self.provider.model_config_version,
                "data_policy_version": request.data_policy_version,
                "source_match_policy_version": (
                    VISUAL_EVIDENCE_SOURCE_MATCH_POLICY_VERSION
                ),
                "payload": request.payload.model_dump(mode="json"),
            }
        )
        raw_output_fingerprint = _canonical_hash(
            detailed.output.model_dump(mode="json")
        )
        try:
            output = validate_visual_evidence_output(
                request.payload.chunk_text,
                detailed.output,
                expected_chunk_id=request.payload.chunk_id,
            )
        except VisualEvidenceContractError as error:
            raise VisualEvidenceContractError(
                error.code,
                output=detailed.output,
                metadata=detailed.metadata,
                input_fingerprint=input_fingerprint,
                output_fingerprint=raw_output_fingerprint,
            ) from error
        reason_codes: list[str] = []
        if output != detailed.output:
            reason_codes.append("source_whitespace_canonicalized")
        if not output.evidence_candidates:
            reason_codes.append("empty_evidence_discovery")
        output_fingerprint = _canonical_hash(output.model_dump(mode="json"))
        return VisualEvidenceDecisionArtifact(
            schema_version=VISUAL_EVIDENCE_ARTIFACT_SCHEMA_VERSION,
            node_id="M1",
            run_id=request.run_id,
            source_document_version_id=request.source_document_version_id,
            chunk_id=request.payload.chunk_id,
            evaluation_attempt_id=request.evaluation_attempt_id,
            contract_version=VISUAL_EVIDENCE_CONTRACT_VERSION,
            prompt_version=VISUAL_EVIDENCE_PROMPT_VERSION,
            prompt_hash=self.provider.prompt_hash,
            model_config_version=self.provider.model_config_version,
            data_policy_version=request.data_policy_version,
            input_fingerprint=input_fingerprint,
            output_fingerprint=output_fingerprint,
            status="completed_with_warnings" if reason_codes else "succeeded",
            reason_codes=tuple(reason_codes),
            counts=VisualEvidenceArtifactCounts(
                mentions=len(output.mentions), evidence_candidates=len(output.evidence_candidates)
            ),
            usage=detailed.metadata,
            output=output,
        )
