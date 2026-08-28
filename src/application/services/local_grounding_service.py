from __future__ import annotations

import hashlib
import json

from novel_character_generator.application.ports.local_grounding import (
    LOCAL_CONTEXT_POLICY_VERSION,
    LOCAL_GROUNDING_ARTIFACT_SCHEMA_VERSION,
    LOCAL_GROUNDING_OUTPUT_SCHEMA_VERSION,
    LOCAL_GROUNDING_POLICY_VERSION,
    AcceptedGroundingStatus,
    GroundedEvidenceSpan,
    GroundedLocalFact,
    GroundedLocalPacket,
    GroundedLocalSignal,
    GroundedMentionNode,
    GroundingIssueReasonCode,
    GroundingIssueRoute,
    GroundingSourceKind,
    LocalContextWindow,
    LocalGroundingArtifactCounts,
    LocalGroundingDecisionArtifact,
    LocalGroundingExecutionRequest,
    LocalGroundingIssue,
    MentionGroundingStatus,
)
from novel_character_generator.application.ports.local_observation import LocalObservationEntity
from novel_character_generator.domain.policies.grounding import (
    EvidenceLocation,
    locate_evidence_span,
)

_SENTENCE_BOUNDARIES = frozenset("。！？!?；;\n")


def _canonical_hash(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _stable_local_id(prefix: str, *parts: str) -> str:
    digest = _canonical_hash(list(parts))[:32]
    return f"{prefix}_{digest}"


def _normalized_text(value: str) -> str:
    return " ".join(value.split()).casefold()


def _accepted_status(location: EvidenceLocation) -> AcceptedGroundingStatus | None:
    if location.status == "exact":
        return "exact"
    if location.status == "normalized":
        return "normalized_unique"
    return None


def _evidence_span(location: EvidenceLocation) -> GroundedEvidenceSpan | None:
    if (
        location.start is None
        or location.end is None
        or location.source_quote is None
        or _accepted_status(location) is None
    ):
        return None
    return GroundedEvidenceSpan(
        start=location.start,
        end=location.end,
        source_quote=location.source_quote,
        quote_hash=hashlib.sha256(location.source_quote.encode("utf-8")).hexdigest(),
    )


def _issue_for_location(
    *,
    source_kind: GroundingSourceKind,
    source_local_id: str,
    local_entity_id: str | None,
    evidence_quote: str,
    location: EvidenceLocation,
) -> LocalGroundingIssue:
    if location.status == "ambiguous":
        route: GroundingIssueRoute = "deferred"
        reason_code: GroundingIssueReasonCode = "ambiguous_evidence"
    elif location.status == "repaired":
        route = "rejected"
        reason_code = "unsupported_quote_repair"
    else:
        route = "rejected"
        reason_code = "quote_not_in_chunk"
    return LocalGroundingIssue(
        route=route,
        source_kind=source_kind,
        source_local_id=source_local_id,
        local_entity_id=local_entity_id,
        evidence_quote=evidence_quote,
        reason_code=reason_code,
        occurrence_count=location.occurrence_count,
    )


def _sentence_context(
    text: str,
    span: GroundedEvidenceSpan,
    *,
    max_chars: int,
) -> LocalContextWindow | None:
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
        evidence_length = span.end - span.start
        remaining = max_chars - evidence_length
        left_budget = remaining // 2
        context_start = max(sentence_start, span.start - left_budget)
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
    return LocalContextWindow(
        policy_version=LOCAL_CONTEXT_POLICY_VERSION,
        start=context_start,
        end=context_end,
        text=context_text,
        focus_start=focus_start,
        focus_end=focus_end,
        context_hash=hashlib.sha256(context_text.encode("utf-8")).hexdigest(),
    )


class LocalGroundingService:
    """Deterministically grounds M1 output without making open-semantic decisions."""

    def ground(self, request: LocalGroundingExecutionRequest) -> LocalGroundingDecisionArtifact:
        mention_nodes = tuple(
            self._ground_mention(request.chunk_text, entity)
            for entity in request.discovery.entities
        )

        rejected_items: list[LocalGroundingIssue] = []
        deferred_items: list[LocalGroundingIssue] = []
        grounded_facts: list[GroundedLocalFact] = []
        grounded_fact_ids: dict[str, str] = {}

        unresolved_keys = {
            (
                item.entity_ref,
                _normalized_text(item.evidence_quote),
                _normalized_text(item.raw_proposition),
            )
            for item in request.discovery.unresolved_items
        }
        fact_key_to_local_id: dict[tuple[str, str, str, str, str], str] = {}
        double_write_fact_ids: set[str] = set()

        for fact in request.discovery.facts:
            shared_key = (
                fact.entity_ref,
                _normalized_text(fact.evidence_quote),
                _normalized_text(fact.raw_proposition),
            )
            if shared_key in unresolved_keys:
                double_write_fact_ids.add(fact.local_fact_id)
                rejected_items.append(
                    LocalGroundingIssue(
                        route="rejected",
                        source_kind="fact",
                        source_local_id=fact.local_fact_id,
                        local_entity_id=fact.entity_ref,
                        evidence_quote=fact.evidence_quote,
                        reason_code="asserted_unresolved_double_write",
                    )
                )
                continue

            fact_key = (
                fact.entity_ref,
                _normalized_text(fact.evidence_quote),
                _normalized_text(fact.raw_proposition),
                fact.coarse_family,
                fact.epistemic_status,
            )
            canonical_local_fact_id = fact_key_to_local_id.get(fact_key)
            if canonical_local_fact_id is not None:
                canonical_grounded_id = grounded_fact_ids.get(canonical_local_fact_id)
                if canonical_grounded_id is not None:
                    grounded_fact_ids[fact.local_fact_id] = canonical_grounded_id
                rejected_items.append(
                    LocalGroundingIssue(
                        route="rejected",
                        source_kind="fact",
                        source_local_id=fact.local_fact_id,
                        local_entity_id=fact.entity_ref,
                        evidence_quote=fact.evidence_quote,
                        reason_code="deterministic_duplicate",
                    )
                )
                continue
            fact_key_to_local_id[fact_key] = fact.local_fact_id

            location = locate_evidence_span(request.chunk_text, fact.evidence_quote)
            status = _accepted_status(location)
            span = _evidence_span(location)
            if status is None or span is None:
                issue = _issue_for_location(
                    source_kind="fact",
                    source_local_id=fact.local_fact_id,
                    local_entity_id=fact.entity_ref,
                    evidence_quote=fact.evidence_quote,
                    location=location,
                )
                (deferred_items if issue.route == "deferred" else rejected_items).append(issue)
                continue

            local_context = _sentence_context(
                request.chunk_text,
                span,
                max_chars=request.max_context_chars,
            )
            if local_context is None:
                deferred_items.append(
                    LocalGroundingIssue(
                        route="deferred",
                        source_kind="fact",
                        source_local_id=fact.local_fact_id,
                        local_entity_id=fact.entity_ref,
                        evidence_quote=fact.evidence_quote,
                        reason_code="local_context_budget_exceeded",
                    )
                )
                continue

            stable_fact_id = _stable_local_id(
                "gf",
                request.run_id,
                request.source_document_version_id,
                request.chunk_id,
                fact.local_fact_id,
            )
            grounded_fact_ids[fact.local_fact_id] = stable_fact_id
            grounded_facts.append(
                GroundedLocalFact(
                    fact_id=stable_fact_id,
                    local_fact_id=fact.local_fact_id,
                    local_entity_id=fact.entity_ref,
                    evidence_quote=span.source_quote,
                    evidence_span=span,
                    grounding_status=status,
                    raw_proposition=fact.raw_proposition,
                    coarse_family=fact.coarse_family,
                    epistemic_status=fact.epistemic_status,
                    local_context=local_context,
                )
            )

        grounded_signals: list[GroundedLocalSignal] = []
        seen_signal_keys: set[tuple[str | None, str | None, str, str]] = set()
        for signal in request.discovery.temporal_signals:
            signal_key = (
                signal.entity_ref,
                signal.fact_ref,
                _normalized_text(signal.evidence_quote),
                signal.signal_kind,
            )
            if signal_key in seen_signal_keys:
                rejected_items.append(
                    LocalGroundingIssue(
                        route="rejected",
                        source_kind="temporal_signal",
                        source_local_id=signal.local_signal_id,
                        local_entity_id=signal.entity_ref,
                        evidence_quote=signal.evidence_quote,
                        reason_code="deterministic_duplicate",
                    )
                )
                continue
            seen_signal_keys.add(signal_key)

            if signal.fact_ref is not None and signal.fact_ref not in grounded_fact_ids:
                deferred_items.append(
                    LocalGroundingIssue(
                        route="deferred",
                        source_kind="temporal_signal",
                        source_local_id=signal.local_signal_id,
                        local_entity_id=signal.entity_ref,
                        evidence_quote=signal.evidence_quote,
                        reason_code="grounded_fact_unavailable",
                    )
                )
                continue

            location = locate_evidence_span(request.chunk_text, signal.evidence_quote)
            status = _accepted_status(location)
            span = _evidence_span(location)
            if status is None or span is None:
                issue = _issue_for_location(
                    source_kind="temporal_signal",
                    source_local_id=signal.local_signal_id,
                    local_entity_id=signal.entity_ref,
                    evidence_quote=signal.evidence_quote,
                    location=location,
                )
                (deferred_items if issue.route == "deferred" else rejected_items).append(issue)
                continue

            grounded_signals.append(
                GroundedLocalSignal(
                    signal_id=_stable_local_id(
                        "gs",
                        request.run_id,
                        request.source_document_version_id,
                        request.chunk_id,
                        signal.local_signal_id,
                    ),
                    local_signal_id=signal.local_signal_id,
                    local_entity_id=signal.entity_ref,
                    grounded_fact_id=(
                        grounded_fact_ids.get(signal.fact_ref)
                        if signal.fact_ref is not None
                        else None
                    ),
                    evidence_quote=span.source_quote,
                    evidence_span=span,
                    grounding_status=status,
                    signal_kind=signal.signal_kind,
                )
            )

        seen_unresolved_keys: set[tuple[str | None, str, str, str]] = set()
        for item in request.discovery.unresolved_items:
            unresolved_shared_key = (
                item.entity_ref,
                _normalized_text(item.evidence_quote),
                _normalized_text(item.raw_proposition),
            )
            unresolved_key = (*unresolved_shared_key, item.reason_code)
            if unresolved_key in seen_unresolved_keys:
                rejected_items.append(
                    LocalGroundingIssue(
                        route="rejected",
                        source_kind="unresolved_item",
                        source_local_id=item.local_item_id,
                        local_entity_id=item.entity_ref,
                        evidence_quote=item.evidence_quote,
                        reason_code="deterministic_duplicate",
                    )
                )
                continue
            seen_unresolved_keys.add(unresolved_key)

            if any(
                fact.local_fact_id in double_write_fact_ids
                and fact.entity_ref == item.entity_ref
                and _normalized_text(fact.evidence_quote) == _normalized_text(item.evidence_quote)
                and _normalized_text(fact.raw_proposition) == _normalized_text(item.raw_proposition)
                for fact in request.discovery.facts
            ):
                rejected_items.append(
                    LocalGroundingIssue(
                        route="rejected",
                        source_kind="unresolved_item",
                        source_local_id=item.local_item_id,
                        local_entity_id=item.entity_ref,
                        evidence_quote=item.evidence_quote,
                        reason_code="asserted_unresolved_double_write",
                        upstream_reason_code=item.reason_code,
                    )
                )
                continue

            location = locate_evidence_span(request.chunk_text, item.evidence_quote)
            status = _accepted_status(location)
            if status is None:
                issue = _issue_for_location(
                    source_kind="unresolved_item",
                    source_local_id=item.local_item_id,
                    local_entity_id=item.entity_ref,
                    evidence_quote=item.evidence_quote,
                    location=location,
                )
                (deferred_items if issue.route == "deferred" else rejected_items).append(issue)
                continue

            deferred_items.append(
                LocalGroundingIssue(
                    route="deferred",
                    source_kind="unresolved_item",
                    source_local_id=item.local_item_id,
                    local_entity_id=item.entity_ref,
                    evidence_quote=item.evidence_quote,
                    reason_code=item.reason_code,
                    upstream_reason_code=item.reason_code,
                    occurrence_count=location.occurrence_count,
                )
            )

        packet = GroundedLocalPacket(
            schema_version=LOCAL_GROUNDING_OUTPUT_SCHEMA_VERSION,
            run_id=request.run_id,
            source_document_version_id=request.source_document_version_id,
            chunk_id=request.chunk_id,
            grounding_policy_version=LOCAL_GROUNDING_POLICY_VERSION,
            context_policy_version=LOCAL_CONTEXT_POLICY_VERSION,
            mention_nodes=mention_nodes,
            grounded_facts=tuple(grounded_facts),
            grounded_signals=tuple(grounded_signals),
            rejected_items=tuple(rejected_items),
            deferred_items=tuple(deferred_items),
        )
        input_fingerprint = _canonical_hash(
            {
                "grounding_policy_version": LOCAL_GROUNDING_POLICY_VERSION,
                "context_policy_version": LOCAL_CONTEXT_POLICY_VERSION,
                "request": request.model_dump(mode="json"),
            }
        )
        output_fingerprint = _canonical_hash(packet.model_dump(mode="json"))
        reason_codes: list[str] = []
        if rejected_items:
            reason_codes.append("rejected_items_present")
        if deferred_items:
            reason_codes.append("deferred_items_present")
        counts = LocalGroundingArtifactCounts(
            mentions=len(mention_nodes),
            grounded_facts=len(grounded_facts),
            grounded_signals=len(grounded_signals),
            rejected_items=len(rejected_items),
            deferred_items=len(deferred_items),
        )
        return LocalGroundingDecisionArtifact(
            schema_version=LOCAL_GROUNDING_ARTIFACT_SCHEMA_VERSION,
            node_id="N2",
            run_id=request.run_id,
            source_document_version_id=request.source_document_version_id,
            chunk_id=request.chunk_id,
            grounding_policy_version=LOCAL_GROUNDING_POLICY_VERSION,
            context_policy_version=LOCAL_CONTEXT_POLICY_VERSION,
            input_fingerprint=input_fingerprint,
            output_fingerprint=output_fingerprint,
            status="completed_with_warnings" if reason_codes else "succeeded",
            reason_codes=tuple(reason_codes),
            counts=counts,
            output=packet,
        )

    @staticmethod
    def _ground_mention(chunk_text: str, entity: LocalObservationEntity) -> GroundedMentionNode:
        mention_quote = entity.mention_quote
        location = locate_evidence_span(chunk_text, mention_quote)
        span = _evidence_span(location)
        if location.status == "exact":
            status: MentionGroundingStatus = "exact"
        elif location.status == "normalized":
            status = "normalized_unique"
        elif location.status == "ambiguous":
            status = "ambiguous"
        elif location.status == "repaired":
            status = "unsupported_repair"
        else:
            status = "not_found"
        return GroundedMentionNode(
            local_entity_id=entity.local_entity_id,
            mention_quote=mention_quote,
            mention_kind=entity.mention_kind,
            representative_name=entity.representative_name,
            grounding_status=status,
            occurrence_count=location.occurrence_count,
            evidence_span=span,
        )
