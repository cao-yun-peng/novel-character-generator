from __future__ import annotations

import json
from dataclasses import dataclass, replace
from hashlib import sha256
from typing import Iterable

from .m1 import M1BoundResult
from .text import SourceSpan, find_safe_quote_matches

DESCRIBE_SUFFIX_RULE_VERSION = "describe-suffix-v1"
DESCRIBE_SUFFIXES = (
    "老者",
    "老人",
    "男子",
    "男人",
    "女子",
    "女人",
    "女孩",
    "少女",
    "姑娘",
    "妇人",
    "老妇",
    "少年",
    "青年",
    "孩童",
)
STABLE_LEXICALIZED_ALIASES = frozenset({"凤姐", "宝二爷"})
GROUNDED_PACKET_VERSION = "grounded-character-packet-v6"
EXACT_EVIDENCE_PRECEDENCE_RULE_VERSION = "exact-evidence-precedence-v1"


def _canonical_hash(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ApprovedEvidence:
    evidence_quote: str
    occurrence_count: int
    source_spans: tuple[SourceSpan, ...]
    relation_to_mention: str
    match_mode: str

    def to_dict(self) -> dict[str, object]:
        return {
            "evidence_quote": self.evidence_quote,
            "occurrence_count": self.occurrence_count,
            "source_spans": [span.to_dict() for span in self.source_spans],
            "relation_to_mention": self.relation_to_mention,
            "match_mode": self.match_mode,
        }


@dataclass(frozen=True)
class GroundedMention:
    local_mention_id: str
    mention_type: str | None
    mention_scope: str | None
    mention_quote: str | None
    approved_evidence: tuple[ApprovedEvidence, ...]
    packet_hash: str

    def to_dict(self) -> dict[str, object]:
        return {
            "local_mention_id": self.local_mention_id,
            "mention_type": self.mention_type,
            "mention_scope": self.mention_scope,
            "mention_quote": self.mention_quote,
            "approved_evidence": [item.to_dict() for item in self.approved_evidence],
            "packet_hash": self.packet_hash,
        }


@dataclass(frozen=True)
class RejectedEvidence:
    mention_index: int
    evidence_quote: str
    reason_code: str

    def to_dict(self) -> dict[str, object]:
        return {
            "mention_index": self.mention_index,
            "evidence_quote": self.evidence_quote,
            "reason_code": self.reason_code,
        }


@dataclass(frozen=True)
class GroundingTraceEvent:
    code: str
    local_mention_id: str
    detail: str

    def to_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "local_mention_id": self.local_mention_id,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class GroundingResult:
    source_document_version_id: str
    chunking_policy_version: str
    chunk_id: str
    chunk_hash: str
    chunk_source_span: SourceSpan
    grounded_mentions: tuple[GroundedMention, ...]
    rejected_evidence: tuple[RejectedEvidence, ...]
    trace_events: tuple[GroundingTraceEvent, ...]
    schema_version: str = GROUNDED_PACKET_VERSION
    evidence_precedence_policy_version: str = EXACT_EVIDENCE_PRECEDENCE_RULE_VERSION

    @property
    def single_character_mentions(self) -> tuple[GroundedMention, ...]:
        """Mentions eligible for later single-character resolution or promotion."""
        return tuple(item for item in self.grounded_mentions if item.mention_scope == "individual")

    @property
    def quarantined_collective_mentions(self) -> tuple[GroundedMention, ...]:
        """Collective evidence retained for audit but barred from person promotion."""
        return tuple(item for item in self.grounded_mentions if item.mention_scope == "collective")

    def to_packet_dict(self) -> dict[str, object]:
        """Serialize the contract packet; service trace remains code-only."""
        return {
            "schema_version": self.schema_version,
            "evidence_precedence_policy_version": self.evidence_precedence_policy_version,
            "source_document_version_id": self.source_document_version_id,
            "chunking_policy_version": self.chunking_policy_version,
            "chunk_id": self.chunk_id,
            "chunk_hash": self.chunk_hash,
            "chunk_source_span": self.chunk_source_span.to_dict(),
            "grounded_mentions": [mention.to_dict() for mention in self.grounded_mentions],
            "rejected_evidence": [item.to_dict() for item in self.rejected_evidence],
        }


def _normalized_mention_type(
    mention_type: str | None,
    mention_scope: str | None,
    mention_quote: str | None,
    recognized_exact_mentions: frozenset[str],
) -> tuple[str | None, bool]:
    if mention_quote is None:
        return None, False
    if mention_scope == "collective":
        return "describe", mention_type != "describe"
    if mention_quote in recognized_exact_mentions or mention_quote in STABLE_LEXICALIZED_ALIASES:
        return "exact", mention_type != "exact"
    if any(mention_quote.endswith(suffix) for suffix in DESCRIBE_SUFFIXES):
        return "describe", mention_type != "describe"
    return mention_type, False


def _packet_hash_input(
    result: M1BoundResult,
    *,
    local_mention_id: str,
    mention_type: str | None,
    mention_scope: str | None,
    mention_quote: str | None,
    approved_evidence: Iterable[ApprovedEvidence],
) -> dict[str, object]:
    occurrences: list[dict[str, object]] = []
    for evidence in approved_evidence:
        for span in evidence.source_spans:
            occurrences.append(
                {
                    "start": span.start,
                    "end": span.end,
                    "relation_to_mention": evidence.relation_to_mention,
                    "match_mode": evidence.match_mode,
                }
            )
    occurrences.sort(
        key=lambda item: (
            int(item["start"]),
            int(item["end"]),
            str(item["relation_to_mention"]),
            str(item["match_mode"]),
        )
    )
    return {
        "grounded_packet_version": GROUNDED_PACKET_VERSION,
        "source_document_version_id": result.envelope.source_document_version_id,
        "chunking_policy_version": result.envelope.chunking_policy_version,
        "chunk_id": result.envelope.chunk_id,
        "chunk_hash": result.envelope.chunk_hash,
        "chunk_source_span": result.envelope.chunk_source_span.to_dict(),
        "local_mention_id": local_mention_id,
        "mention_type": mention_type,
        "mention_scope": mention_scope,
        "mention_quote": mention_quote,
        "evidence_precedence_policy_version": EXACT_EVIDENCE_PRECEDENCE_RULE_VERSION,
        "approved_evidence_occurrences": occurrences,
    }


def _ground_evidence_quote(
    chunk_text: str,
    model_quote: str,
) -> tuple[tuple[str, tuple[SourceSpan, ...], str], ...]:
    """Return raw-source quote groups, preferring byte-for-byte exact matches."""
    matches = find_safe_quote_matches(chunk_text, model_quote)
    grouped: dict[tuple[str, str], list[SourceSpan]] = {}
    for match in matches:
        grouped.setdefault((match.raw_quote, match.match_mode), []).append(match.span)
    return tuple(
        (raw_quote, tuple(spans), match_mode)
        for (raw_quote, match_mode), spans in grouped.items()
    )


def _apply_exact_evidence_precedence(
    result: M1BoundResult,
    grounded_mentions: Iterable[GroundedMention],
    traces: list[GroundingTraceEvent],
) -> tuple[GroundedMention, ...]:
    """Remove exact-owned raw evidence quotes from every describe block."""
    mentions = tuple(grounded_mentions)
    exact_owners: dict[str, list[str]] = {}
    for mention in mentions:
        if mention.mention_type != "exact":
            continue
        for evidence in mention.approved_evidence:
            owners = exact_owners.setdefault(evidence.evidence_quote, [])
            if mention.local_mention_id not in owners:
                owners.append(mention.local_mention_id)

    if not exact_owners:
        return mentions

    filtered_mentions: list[GroundedMention] = []
    for mention in mentions:
        if mention.mention_type != "describe":
            filtered_mentions.append(mention)
            continue

        retained: list[ApprovedEvidence] = []
        for evidence in mention.approved_evidence:
            exact_mentions = exact_owners.get(evidence.evidence_quote)
            if exact_mentions is None:
                retained.append(evidence)
                continue
            traces.append(
                GroundingTraceEvent(
                    code="describe_evidence_shadowed_by_exact",
                    local_mention_id=mention.local_mention_id,
                    detail=(
                        f"occurrences={evidence.occurrence_count}; "
                        f"exact_mentions={','.join(exact_mentions)}; "
                        f"rule={EXACT_EVIDENCE_PRECEDENCE_RULE_VERSION}"
                    ),
                )
            )

        if not retained:
            traces.append(
                GroundingTraceEvent(
                    code="describe_removed_after_exact_dedup",
                    local_mention_id=mention.local_mention_id,
                    detail=f"rule={EXACT_EVIDENCE_PRECEDENCE_RULE_VERSION}",
                )
            )
            continue
        if len(retained) == len(mention.approved_evidence):
            filtered_mentions.append(mention)
            continue

        packet_hash = _canonical_hash(
            _packet_hash_input(
                result,
                local_mention_id=mention.local_mention_id,
                mention_type=mention.mention_type,
                mention_scope=mention.mention_scope,
                mention_quote=mention.mention_quote,
                approved_evidence=retained,
            )
        )
        filtered_mentions.append(
            replace(
                mention,
                approved_evidence=tuple(retained),
                packet_hash=packet_hash,
            )
        )
    return tuple(filtered_mentions)


def ground_m1_result(
    result: M1BoundResult,
    *,
    recognized_exact_mentions: frozenset[str] = frozenset(),
) -> GroundingResult:
    """Deterministically bind M1 quotes to raw Chunk occurrences (the N2 gate)."""
    chunk_text = result.envelope.model_input.chunk_text
    grounded_mentions: list[GroundedMention] = []
    rejected: list[RejectedEvidence] = []
    traces: list[GroundingTraceEvent] = []

    for mention_index, bound in enumerate(result.mentions):
        candidate = bound.candidate
        if candidate.mention_quote is not None and candidate.mention_quote not in chunk_text:
            for evidence_quote in candidate.evidence_quotes:
                rejected.append(RejectedEvidence(mention_index, evidence_quote, "mention_not_in_chunk"))
            continue

        mention_type, normalized = _normalized_mention_type(
            candidate.mention_type,
            candidate.mention_scope,
            candidate.mention_quote,
            recognized_exact_mentions,
        )
        if normalized:
            traces.append(
                GroundingTraceEvent(
                    code="mention_type_normalized_by_suffix",
                    local_mention_id=bound.local_mention_id,
                    detail=f"{candidate.mention_type!r} -> {mention_type!r} by {DESCRIBE_SUFFIX_RULE_VERSION}",
                )
            )

        approved: list[ApprovedEvidence] = []
        seen: set[str] = set()
        for evidence_quote in candidate.evidence_quotes:
            if evidence_quote in seen:
                rejected.append(RejectedEvidence(mention_index, evidence_quote, "duplicate_within_mention"))
                continue
            seen.add(evidence_quote)
            evidence_matches = _ground_evidence_quote(chunk_text, evidence_quote)
            if not evidence_matches:
                rejected.append(RejectedEvidence(mention_index, evidence_quote, "evidence_not_in_chunk"))
                continue
            for raw_quote, evidence_spans, match_mode in evidence_matches:
                if candidate.mention_quote is None:
                    relation = "no_mention"
                elif candidate.mention_quote in raw_quote:
                    relation = "contains_mention"
                else:
                    relation = "contextual"
                approved.append(
                    ApprovedEvidence(
                        evidence_quote=raw_quote,
                        occurrence_count=len(evidence_spans),
                        source_spans=evidence_spans,
                        relation_to_mention=relation,
                        match_mode=match_mode,
                    )
                )
        if not approved:
            continue

        packet_hash = _canonical_hash(
            _packet_hash_input(
                result,
                local_mention_id=bound.local_mention_id,
                mention_type=mention_type,
                mention_scope=candidate.mention_scope,
                mention_quote=candidate.mention_quote,
                approved_evidence=approved,
            )
        )
        grounded_mentions.append(
            GroundedMention(
                local_mention_id=bound.local_mention_id,
                mention_type=mention_type,
                mention_scope=candidate.mention_scope,
                mention_quote=candidate.mention_quote,
                approved_evidence=tuple(approved),
                packet_hash=packet_hash,
            )
        )

    filtered_mentions = _apply_exact_evidence_precedence(result, grounded_mentions, traces)
    envelope = result.envelope
    return GroundingResult(
        source_document_version_id=envelope.source_document_version_id,
        chunking_policy_version=envelope.chunking_policy_version,
        chunk_id=envelope.chunk_id,
        chunk_hash=envelope.chunk_hash,
        chunk_source_span=envelope.chunk_source_span,
        grounded_mentions=filtered_mentions,
        rejected_evidence=tuple(rejected),
        trace_events=tuple(traces),
    )
