from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from typing import Iterable, Sequence

from .errors import ContractValidationError
from .grounding import GroundedMention, GroundingResult
from .m2 import (
    DescribeEvidenceRef,
    LocalCharacterRef,
    M2GroundedAttributionResult,
    M2GroundedFact,
    RemainingEvidenceFragment,
)
from .text import SourceSpan

N3_CHUNK_RESULT_VERSION = "n3-chunk-resolution-v1"
N3_TARGET_PACKET_VERSION = "n3-validated-appearance-packet-v4"
N3_POOL_RESULT_VERSION = "describe-pool-resolution-v4"
N3_RESOLVER_VERSION = "n3-span-arbitration-v1"


def _canonical_hash(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(payload.encode("utf-8")).hexdigest()


def _overlaps(left: SourceSpan, right: SourceSpan) -> bool:
    return left.start < right.end and right.start < left.end


def _merge_spans(spans: Iterable[SourceSpan]) -> tuple[SourceSpan, ...]:
    merged: list[SourceSpan] = []
    for span in sorted(spans, key=lambda item: (item.start, item.end)):
        if merged and span.start <= merged[-1].end:
            merged[-1] = SourceSpan(merged[-1].start, max(merged[-1].end, span.end))
        else:
            merged.append(span)
    return tuple(merged)


def _subtract_span(source: SourceSpan, blockers: Iterable[SourceSpan]) -> tuple[SourceSpan, ...]:
    intersections = _merge_spans(
        SourceSpan(max(source.start, blocker.start), min(source.end, blocker.end))
        for blocker in blockers
        if _overlaps(source, blocker)
    )
    gaps: list[SourceSpan] = []
    cursor = source.start
    for span in intersections:
        if cursor < span.start:
            gaps.append(SourceSpan(cursor, span.start))
        cursor = max(cursor, span.end)
    if cursor < source.end:
        gaps.append(SourceSpan(cursor, source.end))
    return tuple(gaps)


@dataclass(frozen=True)
class N3TargetAppearancePacket:
    target_character_ref: LocalCharacterRef
    grounded_appearance_facts: tuple[M2GroundedFact, ...]
    schema_version: str = N3_TARGET_PACKET_VERSION

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "target_character_ref": self.target_character_ref.to_dict(),
            "grounded_appearance_facts": [fact.to_dict() for fact in self.grounded_appearance_facts],
        }


@dataclass(frozen=True)
class N3ConsumedFragment:
    assigned_target_local_mention_id: str
    fact_quote: str
    fact_chunk_span: SourceSpan
    source_evidence_quote: str
    source_evidence_span: SourceSpan
    status: str = "uniquely_assigned"

    def to_dict(self) -> dict[str, object]:
        return {
            "assigned_target_local_mention_id": self.assigned_target_local_mention_id,
            "fact_quote": self.fact_quote,
            "fact_chunk_span": self.fact_chunk_span.to_dict(),
            "source_evidence_quote": self.source_evidence_quote,
            "source_evidence_span": self.source_evidence_span.to_dict(),
            "status": self.status,
        }


@dataclass(frozen=True)
class N3ConflictFragment:
    conflicted_quote: str
    conflicted_chunk_span: SourceSpan
    source_evidence_quote: str
    source_evidence_span: SourceSpan
    competing_target_local_mention_ids: tuple[str, ...]
    status: str = "cross_target_overlap"

    def to_dict(self) -> dict[str, object]:
        return {
            "conflicted_quote": self.conflicted_quote,
            "conflicted_chunk_span": self.conflicted_chunk_span.to_dict(),
            "source_evidence_quote": self.source_evidence_quote,
            "source_evidence_span": self.source_evidence_span.to_dict(),
            "competing_target_local_mention_ids": list(self.competing_target_local_mention_ids),
            "status": self.status,
        }


@dataclass(frozen=True)
class N3DescribePoolResult:
    chunk_id: str
    describe_source_ref: DescribeEvidenceRef
    consumed_fragments: tuple[N3ConsumedFragment, ...]
    conflicted_fragments: tuple[N3ConflictFragment, ...]
    remaining_evidence_fragments: tuple[RemainingEvidenceFragment, ...]
    progress_made: bool
    next_action: str
    pool_hash: str
    resolver_version: str = N3_RESOLVER_VERSION
    schema_version: str = N3_POOL_RESULT_VERSION

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "chunk_id": self.chunk_id,
            "describe_source_ref": self.describe_source_ref.to_dict(),
            "resolver_version": self.resolver_version,
            "consumed_fragments": [item.to_dict() for item in self.consumed_fragments],
            "conflicted_fragments": [item.to_dict() for item in self.conflicted_fragments],
            "remaining_evidence_fragments": [item.to_dict() for item in self.remaining_evidence_fragments],
            "progress_made": self.progress_made,
            "next_action": self.next_action,
            "pool_hash": self.pool_hash,
        }


@dataclass(frozen=True)
class N3ChunkResolutionResult:
    source_document_version_id: str
    chunk_id: str
    target_appearance_packets: tuple[N3TargetAppearancePacket, ...]
    describe_pool_results: tuple[N3DescribePoolResult, ...]
    schema_version: str = N3_CHUNK_RESULT_VERSION

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "source_document_version_id": self.source_document_version_id,
            "chunk_id": self.chunk_id,
            "target_appearance_packets": [item.to_dict() for item in self.target_appearance_packets],
            "describe_pool_results": [item.to_dict() for item in self.describe_pool_results],
        }


@dataclass(frozen=True)
class _Claim:
    target_id: str
    fact: M2GroundedFact


def _fact_identity(fact: M2GroundedFact) -> tuple[object, ...]:
    return (
        fact.source_mention_id,
        fact.source_evidence_span,
        fact.fact_chunk_span,
        fact.category,
        fact.attribute,
        fact.value,
    )


def _validate_grounded_fact(fact: M2GroundedFact, chunk_text: str) -> None:
    if fact.source_evidence_span.quote(chunk_text) != fact.source_evidence_quote:
        raise ContractValidationError("M2 fact source evidence span does not match N3 chunk_text")
    if fact.fact_chunk_span.quote(chunk_text) != fact.fact_quote:
        raise ContractValidationError("M2 fact span does not match N3 chunk_text")
    if not (
        fact.source_evidence_span.start <= fact.fact_chunk_span.start
        and fact.fact_chunk_span.end <= fact.source_evidence_span.end
    ):
        raise ContractValidationError("M2 fact span is outside its source evidence")


def _evidence_occurrences(mention: GroundedMention, chunk_text: str) -> tuple[tuple[str, SourceSpan], ...]:
    occurrences: list[tuple[str, SourceSpan]] = []
    for evidence in mention.approved_evidence:
        for span in evidence.source_spans:
            if span.quote(chunk_text) != evidence.evidence_quote:
                raise ContractValidationError("N3 source evidence span does not match chunk_text")
            occurrences.append((evidence.evidence_quote, span))
    return tuple(sorted(occurrences, key=lambda item: (item[1].start, item[1].end)))


def resolve_n3_chunk(
    grounding: GroundingResult,
    m2_results: Sequence[M2GroundedAttributionResult],
    *,
    chunk_text: str,
) -> N3ChunkResolutionResult:
    """Arbitrate M2 describe claims and rebuild non-conflict remaining pools."""
    if grounding.chunk_hash and grounding.chunk_hash != sha256(chunk_text.encode("utf-8")).hexdigest():
        raise ContractValidationError("N3 chunk_text hash mismatch")
    exact_mentions = tuple(
        item for item in grounding.single_character_mentions if item.mention_type == "exact"
    )
    describe_mentions = tuple(
        item for item in grounding.single_character_mentions if item.mention_type == "describe"
    )
    exact_ids = {item.local_mention_id for item in exact_mentions}
    result_ids = [item.target_character_ref.local_mention_id for item in m2_results]
    if set(result_ids) != exact_ids or len(result_ids) != len(set(result_ids)):
        raise ContractValidationError("N3 requires exactly one M2 result for every individual exact mention")
    if any(item.target_character_ref.chunk_id != grounding.chunk_id for item in m2_results):
        raise ContractValidationError("M2 result chunk does not match N3 grounding")

    results_by_target = {item.target_character_ref.local_mention_id: item for item in m2_results}
    target_facts: dict[str, list[M2GroundedFact]] = {item.local_mention_id: [] for item in exact_mentions}
    claims_by_describe: dict[str, list[_Claim]] = {item.local_mention_id: [] for item in describe_mentions}
    seen_by_target: dict[str, set[tuple[object, ...]]] = {item.local_mention_id: set() for item in exact_mentions}

    for exact in exact_mentions:
        result = results_by_target[exact.local_mention_id]
        if (
            result.target_character_ref.source_document_version_id
            != grounding.source_document_version_id
            or result.target_character_ref.packet_hash != exact.packet_hash
        ):
            raise ContractValidationError("M2 target ref does not match the N2 exact packet")
        for fact in result.grounded_belongs_to_target:
            _validate_grounded_fact(fact, chunk_text)
            if fact.source_mention_type == "exact":
                if fact.source_mention_id != exact.local_mention_id:
                    raise ContractValidationError("exact fact was bound to a different exact source")
                identity = _fact_identity(fact)
                if identity not in seen_by_target[exact.local_mention_id]:
                    seen_by_target[exact.local_mention_id].add(identity)
                    target_facts[exact.local_mention_id].append(fact)
            elif fact.source_mention_type == "describe":
                if fact.source_mention_id not in claims_by_describe:
                    raise ContractValidationError("M2 fact references an unavailable describe source")
                identity = _fact_identity(fact)
                if identity not in seen_by_target[exact.local_mention_id]:
                    seen_by_target[exact.local_mention_id].add(identity)
                    claims_by_describe[fact.source_mention_id].append(
                        _Claim(exact.local_mention_id, fact)
                    )
            else:
                raise ContractValidationError("M2 grounded fact has invalid source_mention_type")

    pool_results: list[N3DescribePoolResult] = []
    for pool_index, mention in enumerate(describe_mentions, start=1):
        claims = claims_by_describe[mention.local_mention_id]
        conflict_indexes: set[int] = set()
        competing: dict[int, set[str]] = {}
        for left_index, left in enumerate(claims):
            for right_index in range(left_index + 1, len(claims)):
                right = claims[right_index]
                if (
                    left.target_id != right.target_id
                    and _overlaps(left.fact.fact_chunk_span, right.fact.fact_chunk_span)
                ):
                    conflict_indexes.update({left_index, right_index})
                    competing.setdefault(left_index, {left.target_id}).add(right.target_id)
                    competing.setdefault(right_index, {right.target_id}).add(left.target_id)

        consumed: list[N3ConsumedFragment] = []
        conflicts: list[N3ConflictFragment] = []
        consumed_spans: list[SourceSpan] = []
        conflict_spans: list[SourceSpan] = []
        for index, claim in enumerate(claims):
            fact = claim.fact
            if index in conflict_indexes:
                conflict_spans.append(fact.fact_chunk_span)
                conflicts.append(
                    N3ConflictFragment(
                        conflicted_quote=fact.fact_quote,
                        conflicted_chunk_span=fact.fact_chunk_span,
                        source_evidence_quote=fact.source_evidence_quote,
                        source_evidence_span=fact.source_evidence_span,
                        competing_target_local_mention_ids=tuple(sorted(competing[index])),
                    )
                )
                continue
            target_facts[claim.target_id].append(fact)
            consumed_spans.append(fact.fact_chunk_span)
            consumed.append(
                N3ConsumedFragment(
                    assigned_target_local_mention_id=claim.target_id,
                    fact_quote=fact.fact_quote,
                    fact_chunk_span=fact.fact_chunk_span,
                    source_evidence_quote=fact.source_evidence_quote,
                    source_evidence_span=fact.source_evidence_span,
                )
            )

        remaining: list[RemainingEvidenceFragment] = []
        fragment_index = 1
        blockers = tuple(consumed_spans + conflict_spans)
        for evidence_quote, evidence_span in _evidence_occurrences(mention, chunk_text):
            for gap in _subtract_span(evidence_span, blockers):
                remaining.append(
                    RemainingEvidenceFragment(
                        fragment_ref=f"d{pool_index}-f{fragment_index}",
                        source_evidence_quote=evidence_quote,
                        source_evidence_span=evidence_span,
                        fragment_quote=gap.quote(chunk_text),
                        fragment_span=gap,
                    )
                )
                fragment_index += 1

        if remaining:
            next_action = "promote_remaining_describe"
        elif conflicts:
            next_action = "defer_unresolved"
        else:
            next_action = "resolved"
        hash_input = {
            "chunk_id": grounding.chunk_id,
            "describe_source_ref": {
                "local_mention_id": mention.local_mention_id,
                "packet_hash": mention.packet_hash,
            },
            "resolver_version": N3_RESOLVER_VERSION,
            "consumed_fragments": [item.to_dict() for item in consumed],
            "conflicted_fragments": [item.to_dict() for item in conflicts],
            "remaining_evidence_fragments": [item.to_dict() for item in remaining],
        }
        pool_results.append(
            N3DescribePoolResult(
                chunk_id=grounding.chunk_id,
                describe_source_ref=DescribeEvidenceRef(mention.local_mention_id, mention.packet_hash),
                consumed_fragments=tuple(consumed),
                conflicted_fragments=tuple(conflicts),
                remaining_evidence_fragments=tuple(remaining),
                progress_made=bool(consumed),
                next_action=next_action,
                pool_hash=_canonical_hash(hash_input),
            )
        )

    target_packets = tuple(
        N3TargetAppearancePacket(
            target_character_ref=results_by_target[mention.local_mention_id].target_character_ref,
            grounded_appearance_facts=tuple(
                sorted(
                    target_facts[mention.local_mention_id],
                    key=lambda fact: (fact.fact_chunk_span.start, fact.fact_chunk_span.end, fact.category),
                )
            ),
        )
        for mention in exact_mentions
    )
    return N3ChunkResolutionResult(
        source_document_version_id=grounding.source_document_version_id,
        chunk_id=grounding.chunk_id,
        target_appearance_packets=target_packets,
        describe_pool_results=tuple(pool_results),
    )
