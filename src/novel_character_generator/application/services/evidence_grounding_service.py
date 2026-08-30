from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from novel_character_generator.application.ports.evidence_grounding import (
    EVIDENCE_CONTEXT_POLICY_VERSION,
    EVIDENCE_GROUNDING_ARTIFACT_SCHEMA_VERSION,
    EVIDENCE_GROUNDING_OUTPUT_SCHEMA_VERSION,
    EVIDENCE_GROUNDING_POLICY_VERSION,
    AcceptedEvidenceGroundingStatus,
    EvidenceContextWindow,
    EvidenceGroundingArtifactCounts,
    EvidenceGroundingDecisionArtifact,
    EvidenceGroundingExecutionRequest,
    EvidenceGroundingIssue,
    EvidenceMentionNode,
    EvidenceSpan,
    GroundedEvidenceItem,
    GroundedEvidencePacket,
    MentionGroundingStatus,
)

_SENTENCE_BOUNDARIES = frozenset("。！？!?；;\n")


@dataclass(frozen=True)
class _SourceLocation:
    status: AcceptedEvidenceGroundingStatus | None
    occurrence_count: int
    start: int | None = None
    end: int | None = None
    source_quote: str | None = None


def _canonical_hash(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _stable_local_id(prefix: str, *parts: str) -> str:
    return f"{prefix}_{_canonical_hash(list(parts))[:32]}"


def _non_whitespace_view(value: str) -> tuple[str, tuple[int, ...]]:
    characters: list[str] = []
    source_positions: list[int] = []
    for index, character in enumerate(value):
        if character.isspace():
            continue
        characters.append(character)
        source_positions.append(index)
    return "".join(characters), tuple(source_positions)


def _all_starts(text: str, quote: str) -> list[int]:
    starts: list[int] = []
    cursor = 0
    while quote and cursor <= len(text) - len(quote):
        start = text.find(quote, cursor)
        if start < 0:
            break
        starts.append(start)
        cursor = start + 1
    return starts


def _locate_source(chunk_text: str, quote: str) -> _SourceLocation:
    normalized_chunk, source_positions = _non_whitespace_view(chunk_text)
    normalized_quote, _ = _non_whitespace_view(quote)
    if not normalized_quote:
        return _SourceLocation(status=None, occurrence_count=0)
    starts = _all_starts(normalized_chunk, normalized_quote)
    if len(starts) != 1:
        return _SourceLocation(status=None, occurrence_count=len(starts))
    start = starts[0]
    raw_start = source_positions[start]
    raw_end = source_positions[start + len(normalized_quote) - 1] + 1
    source_quote = chunk_text[raw_start:raw_end]
    status: AcceptedEvidenceGroundingStatus = (
        "exact" if source_quote == quote else "whitespace_unique"
    )
    return _SourceLocation(
        status=status,
        occurrence_count=1,
        start=raw_start,
        end=raw_end,
        source_quote=source_quote,
    )


def _span(location: _SourceLocation) -> EvidenceSpan | None:
    if (
        location.status is None
        or location.start is None
        or location.end is None
        or location.source_quote is None
    ):
        return None
    return EvidenceSpan(
        start=location.start,
        end=location.end,
        source_quote=location.source_quote,
        quote_hash=hashlib.sha256(location.source_quote.encode("utf-8")).hexdigest(),
    )


def _sentence_context(
    text: str,
    span: EvidenceSpan,
    *,
    max_chars: int,
) -> EvidenceContextWindow | None:
    if span.end - span.start > max_chars:
        return None
    sentence_start = span.start
    while sentence_start > 0 and text[sentence_start - 1] not in _SENTENCE_BOUNDARIES:
        sentence_start -= 1
    sentence_end = span.end
    while sentence_end < len(text):
        character = text[sentence_end]
        sentence_end += 1
        if character in _SENTENCE_BOUNDARIES:
            break
    while sentence_start < span.start and text[sentence_start].isspace():
        sentence_start += 1
    while sentence_end > span.end and text[sentence_end - 1].isspace():
        sentence_end -= 1

    if sentence_end - sentence_start > max_chars:
        focus_length = span.end - span.start
        remaining = max_chars - focus_length
        context_start = max(sentence_start, span.start - remaining // 2)
        context_end = min(sentence_end, context_start + max_chars)
        if context_end < span.end:
            context_end = span.end
            context_start = max(sentence_start, context_end - max_chars)
    else:
        context_start = sentence_start
        context_end = sentence_end

    context_text = text[context_start:context_end]
    focus_start = span.start - context_start
    focus_end = span.end - context_start
    if context_text[focus_start:focus_end] != span.source_quote:
        return None
    return EvidenceContextWindow(
        policy_version=EVIDENCE_CONTEXT_POLICY_VERSION,
        start=context_start,
        end=context_end,
        text=context_text,
        focus_start=focus_start,
        focus_end=focus_end,
        context_hash=hashlib.sha256(context_text.encode("utf-8")).hexdigest(),
    )


class EvidenceGroundingService:
    """Ground M1 v2 evidence without semantic interpretation or persistence."""

    def ground(
        self, request: EvidenceGroundingExecutionRequest
    ) -> EvidenceGroundingDecisionArtifact:
        mention_nodes: list[EvidenceMentionNode] = []
        for mention in request.discovery.mentions:
            location = _locate_source(request.chunk_text, mention.mention_quote)
            evidence_span = _span(location)
            if location.status is not None:
                mention_status: MentionGroundingStatus = location.status
            elif location.occurrence_count > 1:
                mention_status = "ambiguous"
            else:
                mention_status = "not_found"
            mention_nodes.append(
                EvidenceMentionNode(
                    local_owner_id=mention.mention_id,
                    mention_quote=mention.mention_quote,
                    grounding_status=mention_status,
                    occurrence_count=location.occurrence_count,
                    evidence_span=evidence_span,
                )
            )

        grounded_candidates: list[GroundedEvidenceItem] = []
        rejected_items: list[EvidenceGroundingIssue] = []
        deferred_items: list[EvidenceGroundingIssue] = []
        seen: set[tuple[str | None, str]] = set()
        for candidate in request.discovery.evidence_candidates:
            location = _locate_source(request.chunk_text, candidate.evidence_quote)
            if location.status is None:
                issue = EvidenceGroundingIssue(
                    source_candidate_id=candidate.candidate_id,
                    local_owner_id=candidate.local_owner_id,
                    evidence_quote=candidate.evidence_quote,
                    reason_code=(
                        "ambiguous_evidence"
                        if location.occurrence_count > 1
                        else "quote_not_in_chunk"
                    ),
                    occurrence_count=location.occurrence_count,
                )
                (deferred_items if location.occurrence_count > 1 else rejected_items).append(
                    issue
                )
                continue

            evidence_span = _span(location)
            assert evidence_span is not None
            duplicate_key = (
                candidate.local_owner_id,
                "".join(evidence_span.source_quote.split()).casefold(),
            )
            if duplicate_key in seen:
                rejected_items.append(
                    EvidenceGroundingIssue(
                        source_candidate_id=candidate.candidate_id,
                        local_owner_id=candidate.local_owner_id,
                        evidence_quote=candidate.evidence_quote,
                        reason_code="deterministic_duplicate",
                        occurrence_count=1,
                    )
                )
                continue
            seen.add(duplicate_key)

            local_context = _sentence_context(
                request.chunk_text,
                evidence_span,
                max_chars=request.max_context_chars,
            )
            if local_context is None:
                deferred_items.append(
                    EvidenceGroundingIssue(
                        source_candidate_id=candidate.candidate_id,
                        local_owner_id=candidate.local_owner_id,
                        evidence_quote=candidate.evidence_quote,
                        reason_code="local_context_budget_exceeded",
                        occurrence_count=1,
                    )
                )
                continue

            grounded_candidates.append(
                GroundedEvidenceItem(
                    candidate_id=_stable_local_id(
                        "ge",
                        request.run_id,
                        request.source_document_version_id,
                        request.chunk_id,
                        candidate.candidate_id,
                    ),
                    source_candidate_id=candidate.candidate_id,
                    local_owner_id=candidate.local_owner_id,
                    evidence_quote=evidence_span.source_quote,
                    evidence_span=evidence_span,
                    grounding_status=location.status,
                    local_context=local_context,
                )
            )

        packet = GroundedEvidencePacket(
            schema_version=EVIDENCE_GROUNDING_OUTPUT_SCHEMA_VERSION,
            run_id=request.run_id,
            source_document_version_id=request.source_document_version_id,
            chunk_id=request.chunk_id,
            grounding_policy_version=EVIDENCE_GROUNDING_POLICY_VERSION,
            context_policy_version=EVIDENCE_CONTEXT_POLICY_VERSION,
            mention_nodes=tuple(mention_nodes),
            grounded_candidates=tuple(grounded_candidates),
            rejected_items=tuple(rejected_items),
            deferred_items=tuple(deferred_items),
        )
        input_fingerprint = _canonical_hash(
            {
                "grounding_policy_version": EVIDENCE_GROUNDING_POLICY_VERSION,
                "context_policy_version": EVIDENCE_CONTEXT_POLICY_VERSION,
                "request": request.model_dump(mode="json"),
            }
        )
        output_fingerprint = _canonical_hash(packet.model_dump(mode="json"))
        reason_codes: list[str] = []
        if rejected_items:
            reason_codes.append("rejected_items_present")
        if deferred_items:
            reason_codes.append("deferred_items_present")
        return EvidenceGroundingDecisionArtifact(
            schema_version=EVIDENCE_GROUNDING_ARTIFACT_SCHEMA_VERSION,
            node_id="N2",
            run_id=request.run_id,
            source_document_version_id=request.source_document_version_id,
            chunk_id=request.chunk_id,
            grounding_policy_version=EVIDENCE_GROUNDING_POLICY_VERSION,
            context_policy_version=EVIDENCE_CONTEXT_POLICY_VERSION,
            input_fingerprint=input_fingerprint,
            output_fingerprint=output_fingerprint,
            status="completed_with_warnings" if reason_codes else "succeeded",
            reason_codes=tuple(reason_codes),
            counts=EvidenceGroundingArtifactCounts(
                mentions=len(mention_nodes),
                grounded_candidates=len(grounded_candidates),
                rejected_items=len(rejected_items),
                deferred_items=len(deferred_items),
            ),
            output=packet,
        )
