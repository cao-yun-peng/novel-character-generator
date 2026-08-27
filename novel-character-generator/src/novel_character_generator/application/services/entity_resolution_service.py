from __future__ import annotations

import json
import unicodedata
from collections import Counter
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from novel_character_generator.application.ports.entity_resolution import (
    EntityConvergenceDecision,
    EntityConvergenceInput,
    EntityConvergenceResult,
    EntityMemoryRecord,
    EntityMentionDecision,
    EntityResolutionInput,
    EntityResolutionResult,
    GroundedCandidatePacket,
)
from novel_character_generator.domain.policies.text_processing import estimate_tokens

ENTITY_MEMORY_SELECTION_POLICY = "entity-memory-selection-v1"
ENTITY_CONVERGENCE_FRONTIER_POLICY = "entity-convergence-frontier-v1"
ENTITY_CONVERGENCE_SHARD_POLICY = "entity-convergence-shard-v2"
ENTITY_CONVERGENCE_REPAIR_POLICY = "entity-convergence-repair-v1"
DEFAULT_CONVERGENCE_INPUT_OVERHEAD_TOKENS = 1_024
CONVERGENCE_OUTPUT_TOKENS_PER_RECORD = 192


@dataclass(frozen=True)
class ResolutionMemorySelection:
    records: tuple[EntityMemoryRecord, ...]
    total_records: int
    exact_match_records: int
    previous_chunk_records: int
    recent_fallback_records: int
    status_before: dict[str, int]
    status_selected: dict[str, int]

    def trace_payload(
        self,
        *,
        updated_memory: list[EntityMemoryRecord] | None = None,
    ) -> dict[str, object]:
        selected_records = len(self.records)
        payload: dict[str, object] = {
            "policy": ENTITY_MEMORY_SELECTION_POLICY,
            "records_before": self.total_records,
            "records_selected": selected_records,
            "records_dropped": self.total_records - selected_records,
            "truncated": selected_records < self.total_records,
            "reason_counts": {
                "exact_match": self.exact_match_records,
                "previous_chunk": self.previous_chunk_records,
                "recent_fallback": self.recent_fallback_records,
            },
            "status_before": self.status_before,
            "status_selected": self.status_selected,
        }
        if updated_memory is not None:
            payload.update(
                {
                    "records_after": len(updated_memory),
                    "records_added": len(updated_memory) - self.total_records,
                    "status_after": _status_counts(updated_memory),
                }
            )
        return payload


@dataclass(frozen=True)
class ConvergenceMemoryFrontier:
    records: tuple[EntityMemoryRecord, ...]
    total_nonstable_records: int
    total_nonstable_mentions: int
    batch_mentions: int
    deferred_records: int
    deferred_mentions: int

    def trace_payload(
        self,
        *,
        stable_context_records: int,
        provider_result: EntityConvergenceResult,
        completed_result: EntityConvergenceResult,
        updated_memory: list[EntityMemoryRecord],
    ) -> dict[str, object]:
        expected = {mention_id for item in self.records for mention_id in item.mention_ids}
        provider_mentions = [
            mention_id for item in provider_result.decisions for mention_id in item.mention_ids
        ]
        provider_counts = Counter(provider_mentions)
        provider_unique = set(provider_mentions)
        provider_covered = expected & provider_unique
        completed_mentions = {
            mention_id
            for item in completed_result.decisions
            for mention_id in item.mention_ids
        }
        action_counts = Counter(item.action for item in completed_result.decisions)
        return {
            "policy": ENTITY_CONVERGENCE_FRONTIER_POLICY,
            "batch_mentions": self.batch_mentions,
            "stable_context_records": stable_context_records,
            "nonstable_records_before": self.total_nonstable_records,
            "frontier_records": len(self.records),
            "deferred_records": self.deferred_records,
            "nonstable_mentions_before": self.total_nonstable_mentions,
            "frontier_mentions": len(expected),
            "deferred_mentions": self.deferred_mentions,
            "provider_decisions": len(provider_result.decisions),
            "provider_mentions_returned": len(provider_mentions),
            "provider_covered_mentions": len(provider_covered),
            "provider_omitted_mentions": len(expected - provider_unique),
            "provider_foreign_mentions": len(provider_unique - expected),
            "provider_duplicate_mentions": sum(
                count - 1 for count in provider_counts.values() if count > 1
            ),
            "provider_coverage_ratio": (
                len(provider_covered) / len(expected) if expected else 1.0
            ),
            "completed_decisions": len(completed_result.decisions),
            "completed_covered_mentions": len(expected & completed_mentions),
            "action_counts": dict(sorted(action_counts.items())),
            "status_after": _status_counts(updated_memory),
        }


@dataclass(frozen=True)
class ConvergenceShard:
    index: int
    request: EntityConvergenceInput
    estimated_input_tokens: int
    estimated_output_tokens: int
    record_count: int
    mention_count: int

    def trace_payload(self) -> dict[str, object]:
        return {
            "shard_index": self.index,
            "records": self.record_count,
            "mentions": self.mention_count,
            "estimated_input_tokens": self.estimated_input_tokens,
            "estimated_output_tokens": self.estimated_output_tokens,
        }


@dataclass(frozen=True)
class ConvergenceShardingPlan:
    shards: tuple[ConvergenceShard, ...]
    max_records: int
    max_mentions: int
    max_input_tokens: int
    max_output_tokens: int
    input_token_overhead: int

    def trace_payload(self) -> dict[str, object]:
        return {
            "policy": ENTITY_CONVERGENCE_SHARD_POLICY,
            "shard_count": len(self.shards),
            "input_estimator": "serialized_payload_plus_provider_overhead_v1",
            "input_token_overhead": self.input_token_overhead,
            "output_estimator": "mention_ids_plus_192_per_record_v1",
            "budget": {
                "max_records": self.max_records,
                "max_mentions": self.max_mentions,
                "max_input_tokens": self.max_input_tokens,
                "max_output_tokens": self.max_output_tokens,
            },
            "max_shard_records": max(
                (item.record_count for item in self.shards), default=0
            ),
            "max_shard_mentions": max(
                (item.mention_count for item in self.shards), default=0
            ),
            "max_estimated_input_tokens": max(
                (item.estimated_input_tokens for item in self.shards), default=0
            ),
            "max_estimated_output_tokens": max(
                (item.estimated_output_tokens for item in self.shards), default=0
            ),
            "shards": [item.trace_payload() for item in self.shards],
        }


@dataclass(frozen=True)
class ConvergenceProviderCoverage:
    accepted_result: EntityConvergenceResult
    missing_record_ids: tuple[str, ...]
    expected_mentions: int
    raw_mentions_returned: int
    raw_unique_mentions: int
    omitted_mentions: int
    uncovered_mentions: int
    foreign_mentions: int
    duplicate_mentions: int
    unsafe_decisions: int

    @property
    def covered_mentions(self) -> int:
        return self.expected_mentions - self.uncovered_mentions

    def trace_payload(self) -> dict[str, object]:
        return {
            "expected_mentions": self.expected_mentions,
            "raw_mentions_returned": self.raw_mentions_returned,
            "raw_unique_mentions": self.raw_unique_mentions,
            "covered_mentions": self.covered_mentions,
            "omitted_mentions": self.omitted_mentions,
            "uncovered_mentions": self.uncovered_mentions,
            "foreign_mentions": self.foreign_mentions,
            "duplicate_mentions": self.duplicate_mentions,
            "unsafe_decisions": self.unsafe_decisions,
            "coverage_ratio": (
                self.covered_mentions / self.expected_mentions
                if self.expected_mentions
                else 1.0
            ),
        }


def _memory_lookup_key(value: str) -> str:
    return "".join(unicodedata.normalize("NFKC", value).casefold().split())


def _memory_names(record: EntityMemoryRecord) -> set[str]:
    return {
        key
        for value in [record.canonical_name, *record.names, *record.explicit_names]
        if value
        for key in [_memory_lookup_key(value)]
        if key
    }


def _status_counts(records: list[EntityMemoryRecord]) -> dict[str, int]:
    counts = Counter(item.status for item in records)
    return {
        "stable": counts["stable"],
        "provisional": counts["provisional"],
        "unresolved": counts["unresolved"],
    }


def select_resolution_memory(
    *,
    packet: GroundedCandidatePacket,
    memory: list[EntityMemoryRecord],
    chunk_ordinal: int,
    max_records: int,
    recent_records: int,
) -> ResolutionMemorySelection:
    """Build a bounded model-facing view without deciding character identity."""
    if max_records < 1:
        raise ValueError("entity_resolution_memory_max_records_must_be_positive")
    if recent_records < 0 or recent_records > max_records:
        raise ValueError("entity_resolution_memory_recent_records_out_of_range")

    candidate_names = {
        key
        for mention in packet.mentions
        for value in (mention.representative_name, mention.mention_text)
        for key in [_memory_lookup_key(value)]
        if key
    }
    ordered = sorted(
        memory,
        key=lambda item: (-item.last_chunk_ordinal, item.memory_id),
    )
    exact = [item for item in ordered if candidate_names & _memory_names(item)]
    exact_ids = {item.memory_id for item in exact}
    previous = [
        item
        for item in ordered
        if item.memory_id not in exact_ids and item.last_chunk_ordinal == chunk_ordinal - 1
    ]
    priority_ids = exact_ids | {item.memory_id for item in previous}
    recent = [item for item in ordered if item.memory_id not in priority_ids][:recent_records]

    selected: list[EntityMemoryRecord] = []
    selected_ids: set[str] = set()
    reason_counts = {"exact": 0, "previous": 0, "recent": 0}
    for reason, candidates in (
        ("exact", exact),
        ("previous", previous),
        ("recent", recent),
    ):
        for item in candidates:
            if len(selected) >= max_records:
                break
            if item.memory_id in selected_ids:
                continue
            selected.append(item)
            selected_ids.add(item.memory_id)
            reason_counts[reason] += 1

    return ResolutionMemorySelection(
        records=tuple(selected),
        total_records=len(memory),
        exact_match_records=reason_counts["exact"],
        previous_chunk_records=reason_counts["previous"],
        recent_fallback_records=reason_counts["recent"],
        status_before=_status_counts(memory),
        status_selected=_status_counts(selected),
    )


def select_convergence_memory_frontier(
    *,
    memory: list[EntityMemoryRecord],
    packets: list[GroundedCandidatePacket],
) -> ConvergenceMemoryFrontier:
    """Select non-stable records touched by mentions in the current convergence batch."""
    batch_mention_ids = {
        mention.mention_id for packet in packets for mention in packet.mentions
    }
    nonstable = [item for item in memory if item.status != "stable"]
    frontier = [
        item for item in nonstable if batch_mention_ids.intersection(item.mention_ids)
    ]
    frontier_ids = {item.memory_id for item in frontier}
    deferred = [item for item in nonstable if item.memory_id not in frontier_ids]
    return ConvergenceMemoryFrontier(
        records=tuple(frontier),
        total_nonstable_records=len(nonstable),
        total_nonstable_mentions=len(
            {mention_id for item in nonstable for mention_id in item.mention_ids}
        ),
        batch_mentions=len(batch_mention_ids),
        deferred_records=len(deferred),
        deferred_mentions=len(
            {mention_id for item in deferred for mention_id in item.mention_ids}
        ),
    )


def _bounded_chapter_text(
    text: str,
    packet: GroundedCandidatePacket,
    *,
    max_tokens: int,
) -> tuple[str, bool]:
    if estimate_tokens(text) <= max_tokens:
        return text, False
    windows: list[tuple[int, int]] = []
    for mention in packet.mentions:
        windows.append((max(0, mention.start - 600), min(len(text), mention.end + 600)))
    for fact in packet.facts:
        windows.append((max(0, fact.start - 600), min(len(text), fact.end + 600)))
    merged: list[tuple[int, int]] = []
    for start, end in sorted(windows):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    bounded = "\n…\n".join(text[start:end] for start, end in merged)
    if estimate_tokens(bounded) > max_tokens:
        raise ValueError("entity_resolution_context_budget_exceeded")
    return bounded, True


def build_resolution_input(
    *,
    chunk_id: UUID,
    chunk_ordinal: int,
    chunk_text: str,
    previous_chunk_tail: str,
    packet: GroundedCandidatePacket,
    memory: list[EntityMemoryRecord],
    max_context_tokens: int,
) -> EntityResolutionInput:
    bounded_text, truncated = _bounded_chapter_text(
        chunk_text, packet, max_tokens=max_context_tokens
    )
    historical = list(
        dict.fromkeys(quote for record in memory for quote in record.evidence_quotes[-4:] if quote)
    )[-256:]
    return EntityResolutionInput(
        chunk_id=chunk_id,
        chunk_ordinal=chunk_ordinal,
        chunk_text=bounded_text,
        text_truncated=truncated,
        previous_chunk_tail=previous_chunk_tail[-4_000:],
        candidates=packet,
        cumulative_memory=memory,
        historical_evidence=historical,
    )


def validate_resolution_result(
    request: EntityResolutionInput, result: EntityResolutionResult
) -> None:
    expected = {mention.mention_id for mention in request.candidates.mentions}
    actual = [decision.mention_id for decision in result.decisions]
    if len(actual) != len(set(actual)) or set(actual) != expected:
        raise ValueError("entity_resolution_decision_coverage_mismatch")
    memory_by_id = {item.memory_id: item for item in request.cumulative_memory}
    historical_mentions = {
        mention_id for item in request.cumulative_memory for mention_id in item.mention_ids
    }
    allowed_evidence = [
        request.chunk_text,
        request.previous_chunk_tail,
        *request.historical_evidence,
    ]
    for decision in result.decisions:
        if decision.target_memory_id is not None and decision.target_memory_id not in memory_by_id:
            raise ValueError("entity_resolution_unknown_memory_target")
        if set(decision.related_mention_ids) - historical_mentions:
            raise ValueError("entity_resolution_unknown_related_mention")
        if any(
            not any(quote in source for source in allowed_evidence if source)
            for quote in decision.evidence_quotes
        ):
            raise ValueError("entity_resolution_evidence_not_found")


def downgrade_unverifiable_resolution_evidence(
    request: EntityResolutionInput,
    result: EntityResolutionResult,
) -> EntityResolutionResult:
    """Fail closed per mention when a provider paraphrases identity evidence.

    This repair never creates or preserves a binding for the affected decision. Structural
    problems such as missing decisions, unknown memory IDs, or foreign related mention IDs are
    deliberately left untouched for the strict validator to reject.
    """

    mentions = {item.mention_id: item for item in request.candidates.mentions}
    allowed_sources = [
        request.chunk_text,
        request.previous_chunk_tail,
        *request.historical_evidence,
    ]
    decisions: list[EntityMentionDecision] = []
    for decision in result.decisions:
        evidence_is_grounded = all(
            any(quote in source for source in allowed_sources if source)
            for quote in decision.evidence_quotes
        )
        mention = mentions.get(decision.mention_id)
        if evidence_is_grounded or mention is None:
            decisions.append(decision)
            continue
        decisions.append(
            decision.model_copy(
                update={
                    "action": "unresolved",
                    "target_memory_id": None,
                    "related_mention_ids": [],
                    "evidence_quotes": [mention.mention_text],
                    "confidence": min(decision.confidence, 0.5),
                    "rationale": "unverifiable_provider_evidence_downgraded_to_unresolved",
                }
            )
        )
    return EntityResolutionResult(decisions=decisions)


def _normalized_name(value: str) -> str:
    return "".join(value.split()).casefold()


def enforce_explicit_name_link_gate(
    request: EntityResolutionInput,
    result: EntityResolutionResult,
) -> EntityResolutionResult:
    """Fail closed when one explicit proper name is linked into another identity."""

    memory_by_id = {item.memory_id: item for item in request.cumulative_memory}
    memory_by_mention = {
        mention_id: item
        for item in request.cumulative_memory
        for mention_id in item.mention_ids
    }
    mentions = {item.mention_id: item for item in request.candidates.mentions}
    decisions: list[EntityMentionDecision] = []
    for decision in result.decisions:
        mention = mentions.get(decision.mention_id)
        if mention is None or mention.mention_kind != "name":
            decisions.append(decision)
            continue
        historical_records = [
            memory_by_mention[item]
            for item in decision.related_mention_ids
            if item in memory_by_mention
        ]
        if decision.target_memory_id is not None:
            target = memory_by_id.get(decision.target_memory_id)
            if target is not None:
                historical_records.append(target)
        historical_explicit_names = {
            _normalized_name(name)
            for record in historical_records
            for name in (
                record.explicit_names
                or ([record.canonical_name] if record.canonical_name else [])
            )
            if name
        }
        current_name = _normalized_name(mention.representative_name)
        if historical_explicit_names and current_name not in historical_explicit_names:
            decisions.append(
                decision.model_copy(
                    update={
                        "action": "unresolved",
                        "target_memory_id": None,
                        "related_mention_ids": [],
                        "evidence_quotes": [mention.mention_text],
                        "confidence": min(decision.confidence, 0.5),
                        "rationale": "conflicting_explicit_name_link_kept_unresolved",
                    }
                )
            )
            continue
        decisions.append(decision)
    return EntityResolutionResult(decisions=decisions)


def apply_resolution_result(
    request: EntityResolutionInput,
    result: EntityResolutionResult,
    *,
    base_memory: list[EntityMemoryRecord] | None = None,
) -> list[EntityMemoryRecord]:
    memory = {
        item.memory_id: item.model_copy(deep=True)
        for item in (base_memory if base_memory is not None else request.cumulative_memory)
    }
    mention_to_memory = {
        mention_id: memory_id
        for memory_id, item in memory.items()
        for mention_id in item.mention_ids
    }
    candidates = {item.mention_id: item for item in request.candidates.mentions}

    for decision in result.decisions:
        mention = candidates[decision.mention_id]
        merge_ids = {
            mention_to_memory[item]
            for item in decision.related_mention_ids
            if item in mention_to_memory
        }
        if decision.action == "link_existing":
            assert decision.target_memory_id is not None
            linked_target = memory[decision.target_memory_id]
            if linked_target.status == "stable":
                # A model link is still provisional for this new mention. Keep the
                # stable character memory and create a batch-scoped pending record;
                # only convergence may publish the new mention's facts.
                target_id = f"pending:{decision.mention_id}"
                pending_target = EntityMemoryRecord(
                    memory_id=target_id,
                    character_id=linked_target.character_id,
                    canonical_name=linked_target.canonical_name,
                    status="provisional",
                    names=linked_target.names,
                    explicit_names=linked_target.explicit_names,
                    last_chunk_ordinal=request.chunk_ordinal,
                )
                memory[target_id] = pending_target
            else:
                target_id = decision.target_memory_id
            merge_ids.discard(decision.target_memory_id)
        else:
            target_id = f"candidate:{decision.mention_id}"

        prior_records = [memory.pop(item) for item in merge_ids if item in memory]
        target_record = memory.get(target_id)
        status: Literal["stable", "provisional", "unresolved"] = (
            "unresolved" if decision.action == "unresolved" else "provisional"
        )
        character_id = None
        canonical_name = None
        if target_record is not None:
            status = target_record.status
            character_id = target_record.character_id
            canonical_name = target_record.canonical_name
        combined = [item for record in prior_records for item in record.mention_ids]
        combined.extend(decision.related_mention_ids)
        combined.append(decision.mention_id)
        names = [item for record in prior_records for item in record.names]
        explicit_names = [item for record in prior_records for item in record.explicit_names]
        if target_record is not None:
            names.extend(target_record.names)
            explicit_names.extend(target_record.explicit_names)
        names.append(mention.representative_name)
        if mention.mention_kind == "name":
            explicit_names.append(mention.representative_name)
        evidence = [item for record in prior_records for item in record.evidence_quotes]
        if target_record is not None:
            evidence.extend(target_record.evidence_quotes)
        evidence.extend(decision.evidence_quotes)
        memory[target_id] = EntityMemoryRecord(
            memory_id=target_id,
            character_id=character_id,
            canonical_name=canonical_name,
            status=status,
            mention_ids=list(
                dict.fromkeys(
                    [
                        *(target_record.mention_ids if target_record is not None else []),
                        *combined,
                    ]
                )
            ),
            names=list(dict.fromkeys(names))[-64:],
            explicit_names=list(dict.fromkeys(explicit_names))[-64:],
            evidence_quotes=list(dict.fromkeys(evidence))[-64:],
            last_chunk_ordinal=request.chunk_ordinal,
        )
    return list(memory.values())


def build_convergence_input(
    *,
    batch_index: int,
    start_chunk_ordinal: int,
    end_chunk_ordinal: int,
    final_batch: bool,
    memory: list[EntityMemoryRecord],
    provisional_memory: list[EntityMemoryRecord],
    chapter_decisions: list[dict[str, object]],
    packets: list[GroundedCandidatePacket],
) -> EntityConvergenceInput:
    stable = [item for item in memory if item.status == "stable"]
    snippets = list(
        dict.fromkeys(
            [
                *(mention.mention_text for packet in packets for mention in packet.mentions),
                *(fact.evidence_quote for packet in packets for fact in packet.facts),
                *(quote for item in provisional_memory for quote in item.evidence_quotes),
            ]
        )
    )
    return EntityConvergenceInput(
        batch_index=batch_index,
        start_chunk_ordinal=start_chunk_ordinal,
        end_chunk_ordinal=end_chunk_ordinal,
        final_batch=final_batch,
        stable_memory=stable,
        provisional_memory=provisional_memory,
        chapter_decisions=chapter_decisions,
        evidence_snippets=snippets[-512:],
    )


def _filter_convergence_chapter_decisions(
    chapter_decisions: list[dict[str, object]],
    mention_ids: set[str],
) -> list[dict[str, object]]:
    filtered_rows: list[dict[str, object]] = []
    for row in chapter_decisions:
        result = row.get("result")
        if not isinstance(result, dict):
            continue
        decisions = result.get("decisions")
        if not isinstance(decisions, list):
            continue
        filtered_decisions: list[object] = []
        for decision in decisions:
            if not isinstance(decision, dict):
                continue
            mention_id = decision.get("mention_id")
            related = decision.get("related_mention_ids")
            related_ids = {
                item for item in related if isinstance(item, str)
            } if isinstance(related, list) else set()
            if mention_id in mention_ids or related_ids.intersection(mention_ids):
                filtered_decisions.append(decision)
        if not filtered_decisions:
            continue
        filtered_result = dict(result)
        filtered_result["decisions"] = filtered_decisions
        filtered_row = dict(row)
        filtered_row["result"] = filtered_result
        filtered_rows.append(filtered_row)
    return filtered_rows


def build_convergence_subset_input(
    request: EntityConvergenceInput,
    records: list[EntityMemoryRecord],
) -> EntityConvergenceInput:
    """Create a model-facing subset while retaining only evidence relevant to its records."""
    mention_ids = {mention_id for item in records for mention_id in item.mention_ids}
    record_quotes = {
        quote for item in records for quote in item.evidence_quotes if quote
    }
    snippets = [
        snippet
        for snippet in request.evidence_snippets
        if any(quote in snippet or snippet in quote for quote in record_quotes)
    ]
    if not snippets and records:
        snippets = list(dict.fromkeys(record_quotes))[-512:]
    return request.model_copy(
        update={
            "provisional_memory": records,
            "chapter_decisions": _filter_convergence_chapter_decisions(
                request.chapter_decisions, mention_ids
            ),
            "evidence_snippets": snippets[-512:],
        }
    )


def estimate_convergence_output_tokens(records: list[EntityMemoryRecord]) -> int:
    """Conservative deterministic estimate for structured convergence decisions."""
    mention_payload = json.dumps(
        [mention_id for item in records for mention_id in item.mention_ids],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return (
        estimate_tokens(mention_payload)
        + CONVERGENCE_OUTPUT_TOKENS_PER_RECORD * len(records)
    )


def plan_convergence_shards(
    request: EntityConvergenceInput,
    *,
    max_records: int,
    max_mentions: int,
    max_input_tokens: int,
    max_output_tokens: int,
    input_token_overhead: int = DEFAULT_CONVERGENCE_INPUT_OVERHEAD_TOKENS,
) -> ConvergenceShardingPlan:
    """Greedily pack whole memory records under four independent request budgets."""
    if max_records < 1:
        raise ValueError("entity_convergence_shard_max_records_must_be_positive")
    if max_mentions < 1:
        raise ValueError("entity_convergence_shard_max_mentions_must_be_positive")
    if max_input_tokens < 1:
        raise ValueError("entity_convergence_shard_max_input_tokens_must_be_positive")
    if max_output_tokens < 1:
        raise ValueError("entity_convergence_shard_max_output_tokens_must_be_positive")
    if input_token_overhead < 0:
        raise ValueError("entity_convergence_input_token_overhead_must_not_be_negative")

    mention_ids = [
        mention_id for item in request.provisional_memory for mention_id in item.mention_ids
    ]
    if len(mention_ids) != len(set(mention_ids)):
        raise ValueError("entity_convergence_frontier_duplicate_mentions")

    def make_shard(records: list[EntityMemoryRecord], index: int) -> ConvergenceShard:
        subset = build_convergence_subset_input(request, records)
        return ConvergenceShard(
            index=index,
            request=subset,
            estimated_input_tokens=(
                estimate_tokens(subset.model_dump_json(exclude_none=True))
                + input_token_overhead
            ),
            estimated_output_tokens=estimate_convergence_output_tokens(records),
            record_count=len(records),
            mention_count=sum(len(item.mention_ids) for item in records),
        )

    def exceeds(shard: ConvergenceShard) -> bool:
        return (
            shard.record_count > max_records
            or shard.mention_count > max_mentions
            or shard.estimated_input_tokens > max_input_tokens
            or shard.estimated_output_tokens > max_output_tokens
        )

    shards: list[ConvergenceShard] = []
    pending: list[EntityMemoryRecord] = []
    for record in request.provisional_memory:
        candidate = make_shard([*pending, record], len(shards))
        if not exceeds(candidate):
            pending.append(record)
            continue
        if pending:
            shards.append(make_shard(pending, len(shards)))
            pending = []
            candidate = make_shard([record], len(shards))
        if exceeds(candidate):
            raise ValueError("entity_convergence_record_exceeds_shard_budget")
        pending.append(record)
    if pending:
        shards.append(make_shard(pending, len(shards)))
    return ConvergenceShardingPlan(
        shards=tuple(shards),
        max_records=max_records,
        max_mentions=max_mentions,
        max_input_tokens=max_input_tokens,
        max_output_tokens=max_output_tokens,
        input_token_overhead=input_token_overhead,
    )


def analyze_convergence_provider_result(
    request: EntityConvergenceInput,
    result: EntityConvergenceResult,
) -> ConvergenceProviderCoverage:
    """Accept only decisions that safely and completely cover whole memory records."""
    record_mentions = {
        item.memory_id: set(item.mention_ids) for item in request.provisional_memory
    }
    mention_to_record = {
        mention_id: item.memory_id
        for item in request.provisional_memory
        for mention_id in item.mention_ids
    }
    expected = set(mention_to_record)
    stable_character_ids = {
        item.character_id for item in request.stable_memory if item.character_id is not None
    }
    raw_mentions = [
        mention_id for item in result.decisions for mention_id in item.mention_ids
    ]
    counts = Counter(raw_mentions)
    duplicated = {mention_id for mention_id, count in counts.items() if count > 1}
    invalid_records: set[str] = {
        mention_to_record[mention_id]
        for mention_id in duplicated
        if mention_id in mention_to_record
    }
    decision_records: list[set[str]] = []
    unsafe_decisions: set[int] = set()
    covered_by_record: dict[str, set[str]] = {
        memory_id: set() for memory_id in record_mentions
    }

    for index, decision in enumerate(result.decisions):
        valid_mentions = set(decision.mention_ids) & expected
        records = {mention_to_record[item] for item in valid_mentions}
        decision_records.append(records)
        for mention_id in valid_mentions:
            covered_by_record[mention_to_record[mention_id]].add(mention_id)
        has_foreign = bool(set(decision.mention_ids) - expected)
        has_duplicate = bool(set(decision.mention_ids) & duplicated)
        evidence_is_grounded = all(
            any(quote in snippet for snippet in request.evidence_snippets)
            for quote in decision.evidence_quotes
        )
        target_is_known = (
            decision.target_character_id is None
            or decision.target_character_id in stable_character_ids
        )
        if has_foreign or has_duplicate or not evidence_is_grounded or not target_is_known:
            unsafe_decisions.add(index)
            invalid_records.update(records)

    for memory_id, mentions in record_mentions.items():
        if covered_by_record[memory_id] != mentions:
            invalid_records.add(memory_id)

    changed = True
    while changed:
        changed = False
        for index, records in enumerate(decision_records):
            if index in unsafe_decisions or not records.intersection(invalid_records):
                continue
            new_records = records - invalid_records
            if new_records:
                invalid_records.update(new_records)
                changed = True
            unsafe_decisions.add(index)

    accepted = [
        decision
        for index, decision in enumerate(result.decisions)
        if index not in unsafe_decisions
        and decision_records[index]
        and not decision_records[index].intersection(invalid_records)
    ]
    uncovered_mentions = sum(
        len(record_mentions[memory_id]) for memory_id in invalid_records
    )
    return ConvergenceProviderCoverage(
        accepted_result=EntityConvergenceResult(decisions=accepted),
        missing_record_ids=tuple(
            item.memory_id
            for item in request.provisional_memory
            if item.memory_id in invalid_records
        ),
        expected_mentions=len(expected),
        raw_mentions_returned=len(raw_mentions),
        raw_unique_mentions=len(set(raw_mentions)),
        omitted_mentions=len(expected - set(raw_mentions)),
        uncovered_mentions=uncovered_mentions,
        foreign_mentions=len(set(raw_mentions) - expected),
        duplicate_mentions=sum(
            count - 1 for count in counts.values() if count > 1
        ),
        unsafe_decisions=len(unsafe_decisions),
    )


def validate_convergence_result(
    request: EntityConvergenceInput, result: EntityConvergenceResult
) -> None:
    expected = {
        mention_id for item in request.provisional_memory for mention_id in item.mention_ids
    }
    actual = [mention_id for item in result.decisions for mention_id in item.mention_ids]
    counts = Counter(actual)
    if set(actual) != expected or any(count != 1 for count in counts.values()):
        raise ValueError("entity_convergence_decision_coverage_mismatch")
    stable_character_ids = {
        item.character_id for item in request.stable_memory if item.character_id is not None
    }
    for decision in result.decisions:
        if (
            decision.target_character_id is not None
            and decision.target_character_id not in stable_character_ids
        ):
            raise ValueError("entity_convergence_unknown_character_target")
        if any(
            not any(quote in snippet for snippet in request.evidence_snippets)
            for quote in decision.evidence_quotes
        ):
            raise ValueError("entity_convergence_evidence_not_found")


def conservatively_complete_convergence_result(
    request: EntityConvergenceInput,
    result: EntityConvergenceResult,
) -> EntityConvergenceResult:
    """Keep structurally unsafe, omitted, or ungrounded mentions unresolved.

    Foreign IDs are discarded. Duplicated valid IDs are removed from every competing decision and
    then covered exactly once by a deterministic keep_unresolved decision.
    """

    expected = {
        mention_id for item in request.provisional_memory for mention_id in item.mention_ids
    }
    actual = [mention_id for item in result.decisions for mention_id in item.mention_ids]
    counts = Counter(actual)
    duplicated = {mention_id for mention_id, count in counts.items() if count > 1}

    memory_by_mention = {
        mention_id: item for item in request.provisional_memory for mention_id in item.mention_ids
    }

    def grounded_quote(mention_ids: list[str]) -> str | None:
        for mention_id in mention_ids:
            memory = memory_by_mention.get(mention_id)
            if memory is None:
                continue
            for quote in memory.evidence_quotes:
                if any(quote in snippet for snippet in request.evidence_snippets):
                    return quote
        return request.evidence_snippets[0] if request.evidence_snippets else None

    decisions: list[EntityConvergenceDecision] = []
    for decision in result.decisions:
        safe_mentions = [
            mention_id
            for mention_id in decision.mention_ids
            if mention_id in expected and mention_id not in duplicated
        ]
        if not safe_mentions:
            continue
        structurally_unsafe = len(safe_mentions) != len(decision.mention_ids)
        evidence_is_grounded = all(
            any(quote in snippet for snippet in request.evidence_snippets)
            for quote in decision.evidence_quotes
        )
        replacement_quote = grounded_quote(safe_mentions)
        if not structurally_unsafe and evidence_is_grounded:
            decisions.append(decision.model_copy(update={"mention_ids": safe_mentions}))
            continue
        if replacement_quote is None:
            return result
        decisions.append(
            decision.model_copy(
                update={
                    "mention_ids": safe_mentions,
                    "action": "keep_unresolved",
                    "target_character_id": None,
                    "canonical_name": None,
                    "creation_key": None,
                    "evidence_quotes": [replacement_quote],
                    "confidence": min(decision.confidence, 0.5),
                    "rationale": "unsafe_provider_decision_kept_unresolved",
                }
            )
        )

    covered = {mention_id for item in decisions for mention_id in item.mention_ids}
    missing = expected - covered
    remaining_missing = set(missing)
    for memory in request.provisional_memory:
        missing_mentions = [item for item in memory.mention_ids if item in remaining_missing]
        if not missing_mentions:
            continue
        quote = grounded_quote(missing_mentions)
        if quote is None:
            return result
        decisions.append(
            EntityConvergenceDecision(
                mention_ids=missing_mentions,
                action="keep_unresolved",
                evidence_quotes=[quote],
                confidence=0.0,
                rationale="provider_omission_kept_unresolved",
            )
        )
        remaining_missing.difference_update(missing_mentions)
    return EntityConvergenceResult(decisions=decisions)


def enforce_explicit_name_convergence_gate(
    request: EntityConvergenceInput,
    result: EntityConvergenceResult,
) -> EntityConvergenceResult:
    """Prevent convergence from publishing groups with conflicting explicit names."""

    memory_by_mention = {
        mention_id: item for item in request.provisional_memory for mention_id in item.mention_ids
    }
    stable_names = {
        item.character_id: _normalized_name(item.canonical_name)
        for item in request.stable_memory
        if item.character_id is not None and item.canonical_name
    }
    decisions: list[EntityConvergenceDecision] = []
    for decision in result.decisions:
        if decision.action in {"keep_unresolved", "reject_candidate"}:
            decisions.append(decision)
            continue
        explicit_names = {
            _normalized_name(name)
            for mention_id in decision.mention_ids
            for record in [memory_by_mention.get(mention_id)]
            if record is not None
            for name in record.explicit_names
            if name
        }
        unsafe = len(explicit_names) > 1
        if decision.action == "confirm_link":
            target_name = (
                stable_names.get(decision.target_character_id)
                if decision.target_character_id is not None
                else None
            )
            unsafe = unsafe or bool(explicit_names and target_name not in explicit_names)
        elif decision.action in {"create_character", "split_candidate"}:
            canonical_name = (
                _normalized_name(decision.canonical_name) if decision.canonical_name else ""
            )
            unsafe = unsafe or bool(explicit_names and canonical_name not in explicit_names)
        if not unsafe:
            decisions.append(decision)
            continue
        decisions.append(
            decision.model_copy(
                update={
                    "action": "keep_unresolved",
                    "target_character_id": None,
                    "canonical_name": None,
                    "creation_key": None,
                    "confidence": min(decision.confidence, 0.5),
                    "rationale": "conflicting_explicit_names_kept_unresolved",
                }
            )
        )
    return EntityConvergenceResult(decisions=decisions)
