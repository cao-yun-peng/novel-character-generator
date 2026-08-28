from uuid import uuid4

import pytest

from novel_character_generator.application.ports.entity_resolution import (
    EntityConvergenceDecision,
    EntityConvergenceInput,
    EntityConvergenceResult,
    EntityMemoryRecord,
    EntityMentionDecision,
    EntityResolutionResult,
    GroundedCandidatePacket,
    GroundedMentionCandidate,
)
from novel_character_generator.application.services.entity_resolution_service import (
    analyze_convergence_provider_result,
    apply_resolution_result,
    build_convergence_input,
    build_resolution_input,
    conservatively_complete_convergence_result,
    downgrade_unverifiable_resolution_evidence,
    enforce_explicit_name_convergence_gate,
    enforce_explicit_name_link_gate,
    plan_convergence_shards,
    select_convergence_memory_frontier,
    select_resolution_memory,
    validate_convergence_result,
    validate_resolution_result,
)
from novel_character_generator.infrastructure.llm.entity_resolution import (
    CONVERGENCE_SYSTEM_PROMPT,
    ENTITY_RESOLUTION_PROMPT_VERSION,
    RESOLUTION_SYSTEM_PROMPT,
)


def _packet(mention_id: str, name: str, text: str, start: int) -> GroundedCandidatePacket:
    return GroundedCandidatePacket(
        mentions=[
            GroundedMentionCandidate(
                mention_id=mention_id,
                local_entity_id="e1",
                representative_name=name,
                mention_text=text,
                mention_kind="name" if name == "唐三" else "title",
                start=start,
                end=start + len(text),
                confidence=1.0,
            )
        ]
    )


def _memory(
    memory_id: str,
    *,
    name: str,
    status: str,
    last_chunk_ordinal: int,
) -> EntityMemoryRecord:
    return EntityMemoryRecord(
        memory_id=memory_id,
        status=status,
        mention_ids=[f"mention:{memory_id}"],
        names=[name],
        explicit_names=[name] if status == "stable" else [],
        evidence_quotes=[name],
        last_chunk_ordinal=last_chunk_ordinal,
    )


def test_resolution_memory_selection_is_bounded_and_priority_ordered() -> None:
    memory = [
        _memory("stable:tang-san", name="唐三", status="stable", last_chunk_ordinal=1),
        _memory("previous:master", name="师父", status="provisional", last_chunk_ordinal=9),
        _memory("recent:one", name="司婆婆", status="stable", last_chunk_ordinal=8),
        _memory("recent:two", name="药师", status="unresolved", last_chunk_ordinal=7),
        _memory("old:blind", name="瞎子", status="stable", last_chunk_ordinal=2),
    ]

    selection = select_resolution_memory(
        packet=_packet("m-current", "唐三", "唐三", 0),
        memory=memory,
        chunk_ordinal=10,
        max_records=3,
        recent_records=1,
    )

    assert [item.memory_id for item in selection.records] == [
        "stable:tang-san",
        "previous:master",
        "recent:one",
    ]
    assert selection.trace_payload() == {
        "policy": "entity-memory-selection-v1",
        "records_before": 5,
        "records_selected": 3,
        "records_dropped": 2,
        "truncated": True,
        "reason_counts": {
            "exact_match": 1,
            "previous_chunk": 1,
            "recent_fallback": 1,
        },
        "status_before": {"stable": 3, "provisional": 1, "unresolved": 1},
        "status_selected": {"stable": 2, "provisional": 1, "unresolved": 0},
    }


def test_applying_selected_resolution_preserves_hidden_base_memory() -> None:
    visible = _memory(
        "visible:tang-san", name="唐三", status="stable", last_chunk_ordinal=1
    )
    hidden = _memory("hidden:blind", name="瞎子", status="stable", last_chunk_ordinal=0)
    request = build_resolution_input(
        chunk_id=uuid4(),
        chunk_ordinal=2,
        chunk_text="另一人站在门外。",
        previous_chunk_tail="",
        packet=_packet("m-new", "另一人", "另一人", 0),
        memory=[visible],
        max_context_tokens=2_000,
    )
    result = EntityResolutionResult(
        decisions=[
            EntityMentionDecision(
                mention_id="m-new",
                action="unresolved",
                evidence_quotes=["另一人"],
                confidence=0.5,
                rationale="insufficient identity evidence",
            )
        ]
    )
    validate_resolution_result(request, result)

    updated = apply_resolution_result(request, result, base_memory=[visible, hidden])

    assert {item.memory_id for item in updated} == {
        "visible:tang-san",
        "hidden:blind",
        "candidate:m-new",
    }
    assert next(item for item in updated if item.memory_id == "hidden:blind") == hidden


def test_convergence_frontier_defers_untouched_unresolved_and_reactivates_dirty_record() -> None:
    stable = _memory(
        "character:stable", name="司婆婆", status="stable", last_chunk_ordinal=1
    )
    untouched = _memory(
        "candidate:untouched", name="旧人", status="unresolved", last_chunk_ordinal=2
    )
    dirty = EntityMemoryRecord(
        memory_id="candidate:dirty",
        status="unresolved",
        mention_ids=["m-old", "m-current"],
        names=["旅人"],
        evidence_quotes=["旅人"],
        last_chunk_ordinal=10,
    )
    packet = _packet("m-current", "旅人", "旅人", 0)

    frontier = select_convergence_memory_frontier(
        memory=[stable, untouched, dirty],
        packets=[packet],
    )
    request = build_convergence_input(
        batch_index=1,
        start_chunk_ordinal=10,
        end_chunk_ordinal=10,
        final_batch=True,
        memory=[stable, untouched, dirty],
        provisional_memory=list(frontier.records),
        chapter_decisions=[],
        packets=[packet],
    )

    assert [item.memory_id for item in request.provisional_memory] == ["candidate:dirty"]
    assert [item.memory_id for item in request.stable_memory] == ["character:stable"]
    assert frontier.total_nonstable_records == 2
    assert frontier.deferred_records == 1
    assert frontier.deferred_mentions == 1

    provider_result = EntityConvergenceResult(
        decisions=[
            EntityConvergenceDecision(
                mention_ids=["m-current"],
                action="keep_unresolved",
                evidence_quotes=["旅人"],
                confidence=0.5,
                rationale="provider omitted the historical member",
            )
        ]
    )
    completed_result = EntityConvergenceResult(
        decisions=[
            EntityConvergenceDecision(
                mention_ids=["m-old", "m-current"],
                action="keep_unresolved",
                evidence_quotes=["旅人"],
                confidence=0.0,
                rationale="conservative completion",
            )
        ]
    )
    trace = frontier.trace_payload(
        stable_context_records=1,
        provider_result=provider_result,
        completed_result=completed_result,
        updated_memory=[stable, untouched, dirty],
    )

    assert trace["frontier_mentions"] == 2
    assert trace["provider_covered_mentions"] == 1
    assert trace["provider_omitted_mentions"] == 1
    assert trace["completed_covered_mentions"] == 2
    assert trace["status_after"] == {
        "stable": 1,
        "provisional": 0,
        "unresolved": 2,
    }


def test_memory_is_cumulative_and_same_generic_label_is_not_auto_linked() -> None:
    first = build_resolution_input(
        chunk_id=uuid4(),
        chunk_ordinal=0,
        chunk_text="山顶上坐着一个男孩。",
        previous_chunk_tail="",
        packet=_packet("m1", "男孩", "男孩", 7),
        memory=[],
        max_context_tokens=2_000,
    )
    first_result = EntityResolutionResult(
        decisions=[
            EntityMentionDecision(
                mention_id="m1",
                action="create_candidate",
                evidence_quotes=["男孩"],
                confidence=0.8,
                rationale="first local mention",
            )
        ]
    )
    validate_resolution_result(first, first_result)
    memory = apply_resolution_result(first, first_result)

    second = build_resolution_input(
        chunk_id=uuid4(),
        chunk_ordinal=1,
        chunk_text="这个男孩正是唐三。",
        previous_chunk_tail=first.chunk_text,
        packet=_packet("m2", "唐三", "唐三", 7),
        memory=memory,
        max_context_tokens=2_000,
    )
    second_result = EntityResolutionResult(
        decisions=[
            EntityMentionDecision(
                mention_id="m2",
                action="link_existing",
                target_memory_id=memory[0].memory_id,
                related_mention_ids=["m1"],
                evidence_quotes=["这个男孩正是唐三"],
                confidence=0.99,
                rationale="explicit identity statement",
            )
        ]
    )
    validate_resolution_result(second, second_result)
    memory = apply_resolution_result(second, second_result)
    assert set(memory[0].mention_ids) == {"m1", "m2"}
    assert {"男孩", "唐三"} <= set(memory[0].names)

    third = build_resolution_input(
        chunk_id=uuid4(),
        chunk_ordinal=2,
        chunk_text="河边又站着一个男孩。",
        previous_chunk_tail=second.chunk_text,
        packet=_packet("m3", "男孩", "男孩", 7),
        memory=memory,
        max_context_tokens=2_000,
    )
    assert set(third.cumulative_memory[0].mention_ids) == {"m1", "m2"}
    third_result = EntityResolutionResult(
        decisions=[
            EntityMentionDecision(
                mention_id="m3",
                action="unresolved",
                evidence_quotes=["男孩"],
                confidence=0.7,
                rationale="same generic label is not identity evidence",
            )
        ]
    )
    validate_resolution_result(third, third_result)
    memory = apply_resolution_result(third, third_result)
    assert len(memory) == 2
    assert next(item for item in memory if "m3" in item.mention_ids).status == "unresolved"


def test_resolution_rejects_evidence_not_present_in_supplied_context() -> None:
    request = build_resolution_input(
        chunk_id=uuid4(),
        chunk_ordinal=0,
        chunk_text="唐三站在山顶。",
        previous_chunk_tail="",
        packet=_packet("m1", "唐三", "唐三", 0),
        memory=[],
        max_context_tokens=2_000,
    )
    result = EntityResolutionResult(
        decisions=[
            EntityMentionDecision(
                mention_id="m1",
                action="create_candidate",
                evidence_quotes=["不存在的原文"],
                confidence=1.0,
                rationale="bad evidence",
            )
        ]
    )
    with pytest.raises(ValueError, match="entity_resolution_evidence_not_found"):
        validate_resolution_result(request, result)


def test_unverifiable_evidence_is_downgraded_without_publishing_a_binding() -> None:
    request = build_resolution_input(
        chunk_id=uuid4(),
        chunk_ordinal=1,
        chunk_text="唐三站在山顶。",
        previous_chunk_tail="",
        packet=_packet("m2", "唐三", "唐三", 0),
        memory=[],
        max_context_tokens=2_000,
    )
    result = EntityResolutionResult(
        decisions=[
            EntityMentionDecision(
                mention_id="m2",
                action="create_candidate",
                evidence_quotes=["模型改写了原文"],
                confidence=0.95,
                rationale="paraphrased evidence",
            )
        ]
    )

    repaired = downgrade_unverifiable_resolution_evidence(request, result)

    decision = repaired.decisions[0]
    assert decision.action == "unresolved"
    assert decision.target_memory_id is None
    assert decision.related_mention_ids == []
    assert decision.evidence_quotes == ["唐三"]
    assert decision.confidence == 0.5
    validate_resolution_result(request, repaired)


def test_resolution_prompt_constrains_related_mentions_to_historical_ids() -> None:
    assert ENTITY_RESOLUTION_PROMPT_VERSION == "entity-resolution-prompt-v1.5"
    assert "Only mention_kind=explicit_name" in RESOLUTION_SYSTEM_PROMPT
    assert "never enter explicit_names" in RESOLUTION_SYSTEM_PROMPT
    assert "cumulative_memory[*].mention_ids" in RESOLUTION_SYSTEM_PROMPT
    assert "Never put the current decision mention_id" in RESOLUTION_SYSTEM_PROMPT
    schema = EntityMentionDecision.model_json_schema()
    description = schema["properties"]["related_mention_ids"]["description"]
    assert "Historical mention IDs" in description
    assert "shortest continuous verbatim substring" in RESOLUTION_SYSTEM_PROMPT
    assert "different explicit proper name" in RESOLUTION_SYSTEM_PROMPT


def test_descriptor_never_enters_explicit_names() -> None:
    packet = GroundedCandidatePacket(
        mentions=[
            GroundedMentionCandidate(
                mention_id="m-girl",
                local_entity_id="e1",
                representative_name="少女",
                mention_text="少女",
                mention_kind="descriptor",
                start=0,
                end=2,
                confidence=0.95,
            )
        ]
    )
    request = build_resolution_input(
        chunk_id=uuid4(),
        chunk_ordinal=0,
        chunk_text="少女站在门边。",
        previous_chunk_tail="",
        packet=packet,
        memory=[],
        max_context_tokens=2_000,
    )
    result = EntityResolutionResult(
        decisions=[
            EntityMentionDecision(
                mention_id="m-girl",
                action="create_candidate",
                evidence_quotes=["少女"],
                confidence=0.8,
                rationale="local descriptor only",
            )
        ]
    )

    memory = apply_resolution_result(request, result)

    assert packet.mentions[0].mention_kind == "descriptor"
    assert memory[0].names == ["少女"]
    assert memory[0].explicit_names == []


def test_explicit_name_link_gate_blocks_cross_person_binding() -> None:
    request = build_resolution_input(
        chunk_id=uuid4(),
        chunk_ordinal=3,
        chunk_text="唐昊抬起头。",
        previous_chunk_tail="唐三站在门边。",
        packet=GroundedCandidatePacket(
            mentions=[
                GroundedMentionCandidate(
                    mention_id="m2",
                    local_entity_id="e2",
                    representative_name="唐昊",
                    mention_text="唐昊",
                    mention_kind="name",
                    start=0,
                    end=2,
                    confidence=0.99,
                )
            ]
        ),
        memory=[
            EntityMemoryRecord(
                memory_id="candidate:tang-san",
                status="provisional",
                mention_ids=["m1"],
                names=["唐三"],
                explicit_names=["唐三"],
                evidence_quotes=["唐三"],
                last_chunk_ordinal=2,
            )
        ],
        max_context_tokens=2_000,
    )
    unsafe = EntityResolutionResult(
        decisions=[
            EntityMentionDecision(
                mention_id="m2",
                action="link_existing",
                target_memory_id="candidate:tang-san",
                related_mention_ids=["m1"],
                evidence_quotes=["唐昊"],
                confidence=0.98,
                rationale="unsafe provider merge",
            )
        ]
    )

    repaired = enforce_explicit_name_link_gate(request, unsafe)

    assert repaired.decisions[0].action == "unresolved"
    assert repaired.decisions[0].target_memory_id is None
    assert repaired.decisions[0].related_mention_ids == []
    assert repaired.decisions[0].rationale == "conflicting_explicit_name_link_kept_unresolved"
    validate_resolution_result(request, repaired)


def test_convergence_prompt_distinguishes_memory_ids_from_character_ids() -> None:
    assert "candidate:* value" in CONVERGENCE_SYSTEM_PROMPT
    assert "copy that character_id" in CONVERGENCE_SYSTEM_PROMPT
    assert "create_character with canonical_name and a stable creation_key" in (
        CONVERGENCE_SYSTEM_PROMPT
    )
    schema = EntityConvergenceDecision.model_json_schema()
    target_description = schema["properties"]["target_character_id"]["description"]
    assert "Never use memory_id" in target_description


def test_convergence_gate_blocks_group_with_two_explicit_names() -> None:
    request = EntityConvergenceInput(
        batch_index=0,
        start_chunk_ordinal=0,
        end_chunk_ordinal=9,
        final_batch=True,
        provisional_memory=[
            EntityMemoryRecord(
                memory_id="candidate:m1",
                status="provisional",
                mention_ids=["m1"],
                explicit_names=["唐三"],
                evidence_quotes=["唐三"],
                last_chunk_ordinal=1,
            ),
            EntityMemoryRecord(
                memory_id="candidate:m2",
                status="provisional",
                mention_ids=["m2"],
                explicit_names=["唐昊"],
                evidence_quotes=["唐昊"],
                last_chunk_ordinal=2,
            ),
        ],
        evidence_snippets=["唐三", "唐昊"],
    )
    unsafe = EntityConvergenceResult(
        decisions=[
            EntityConvergenceDecision(
                mention_ids=["m1", "m2"],
                action="create_character",
                canonical_name="唐三",
                creation_key="tang-san",
                evidence_quotes=["唐三", "唐昊"],
                confidence=0.95,
                rationale="unsafe group",
            )
        ]
    )

    repaired = enforce_explicit_name_convergence_gate(request, unsafe)

    assert repaired.decisions[0].action == "keep_unresolved"
    assert repaired.decisions[0].canonical_name is None
    assert repaired.decisions[0].creation_key is None
    validate_convergence_result(request, repaired)


def test_convergence_omissions_are_kept_unresolved_without_inventing_a_character() -> None:
    request = EntityConvergenceInput(
        batch_index=0,
        start_chunk_ordinal=0,
        end_chunk_ordinal=9,
        final_batch=True,
        provisional_memory=[
            EntityMemoryRecord(
                memory_id="candidate:one",
                status="provisional",
                mention_ids=["m1", "m2"],
                names=["唐三"],
                evidence_quotes=["唐三"],
                last_chunk_ordinal=9,
            )
        ],
        evidence_snippets=["唐三"],
    )
    result = EntityConvergenceResult(
        decisions=[
            EntityConvergenceDecision(
                mention_ids=["m1"],
                action="create_character",
                canonical_name="唐三",
                creation_key="tang-san",
                evidence_quotes=["唐三"],
                confidence=0.9,
                rationale="explicit name",
            )
        ]
    )

    repaired = conservatively_complete_convergence_result(request, result)

    assert repaired.decisions[0].action == "create_character"
    omitted = repaired.decisions[1]
    assert omitted.mention_ids == ["m2"]
    assert omitted.action == "keep_unresolved"
    assert omitted.target_character_id is None
    assert omitted.confidence == 0.0
    validate_convergence_result(request, repaired)


def test_convergence_foreign_or_duplicate_mentions_are_discarded_and_kept_unresolved() -> None:
    request = EntityConvergenceInput(
        batch_index=0,
        start_chunk_ordinal=0,
        end_chunk_ordinal=0,
        final_batch=True,
        provisional_memory=[
            EntityMemoryRecord(
                memory_id="candidate:one",
                status="unresolved",
                mention_ids=["m1"],
                evidence_quotes=["男孩"],
                last_chunk_ordinal=0,
            )
        ],
        evidence_snippets=["男孩"],
    )
    invalid = EntityConvergenceResult(
        decisions=[
            EntityConvergenceDecision(
                mention_ids=["foreign"],
                action="keep_unresolved",
                evidence_quotes=["男孩"],
                confidence=0.5,
                rationale="invalid id",
            )
        ]
    )

    repaired = conservatively_complete_convergence_result(request, invalid)

    assert len(repaired.decisions) == 1
    assert repaired.decisions[0].mention_ids == ["m1"]
    assert repaired.decisions[0].action == "keep_unresolved"
    assert repaired.decisions[0].confidence == 0.0
    validate_convergence_result(request, repaired)


def test_convergence_duplicate_valid_mentions_are_not_allowed_to_choose_a_binding() -> None:
    request = EntityConvergenceInput(
        batch_index=0,
        start_chunk_ordinal=0,
        end_chunk_ordinal=0,
        final_batch=True,
        provisional_memory=[
            EntityMemoryRecord(
                memory_id="candidate:one",
                status="provisional",
                mention_ids=["m1"],
                evidence_quotes=["唐三"],
                last_chunk_ordinal=0,
            )
        ],
        evidence_snippets=["唐三"],
    )
    duplicated = EntityConvergenceResult(
        decisions=[
            EntityConvergenceDecision(
                mention_ids=["m1"],
                action="create_character",
                canonical_name="唐三",
                creation_key="one",
                evidence_quotes=["唐三"],
                confidence=0.9,
                rationale="first",
            ),
            EntityConvergenceDecision(
                mention_ids=["m1"],
                action="create_character",
                canonical_name="另一个唐三",
                creation_key="two",
                evidence_quotes=["唐三"],
                confidence=0.8,
                rationale="second",
            ),
        ]
    )

    repaired = conservatively_complete_convergence_result(request, duplicated)

    assert len(repaired.decisions) == 1
    assert repaired.decisions[0].mention_ids == ["m1"]
    assert repaired.decisions[0].action == "keep_unresolved"
    validate_convergence_result(request, repaired)


def test_convergence_duplicate_memory_ownership_is_covered_only_once() -> None:
    request = EntityConvergenceInput(
        batch_index=1,
        start_chunk_ordinal=10,
        end_chunk_ordinal=18,
        final_batch=True,
        provisional_memory=[
            EntityMemoryRecord(
                memory_id="candidate:one",
                status="unresolved",
                mention_ids=["m1"],
                evidence_quotes=["唐三"],
                last_chunk_ordinal=18,
            ),
            EntityMemoryRecord(
                memory_id="candidate:two",
                status="unresolved",
                mention_ids=["m1"],
                evidence_quotes=["唐三"],
                last_chunk_ordinal=18,
            ),
        ],
        evidence_snippets=["唐三"],
    )

    repaired = conservatively_complete_convergence_result(
        request,
        EntityConvergenceResult(),
    )

    assert len(repaired.decisions) == 1
    assert repaired.decisions[0].mention_ids == ["m1"]
    assert repaired.decisions[0].action == "keep_unresolved"
    validate_convergence_result(request, repaired)


def test_convergence_frontier_is_sharded_by_atomic_record_and_mention_budget() -> None:
    request = EntityConvergenceInput(
        batch_index=0,
        start_chunk_ordinal=0,
        end_chunk_ordinal=9,
        final_batch=False,
        provisional_memory=[
            EntityMemoryRecord(
                memory_id=f"candidate:{index}",
                status="unresolved",
                mention_ids=[f"m{index}"],
                evidence_quotes=[f"人物{index}"],
                last_chunk_ordinal=index,
            )
            for index in range(3)
        ],
        evidence_snippets=["人物0", "人物1", "人物2"],
    )

    plan = plan_convergence_shards(
        request,
        max_records=100,
        max_mentions=2,
        max_input_tokens=100_000,
        max_output_tokens=100_000,
    )

    assert [item.mention_count for item in plan.shards] == [2, 1]
    assert [
        [record.memory_id for record in item.request.provisional_memory]
        for item in plan.shards
    ] == [["candidate:0", "candidate:1"], ["candidate:2"]]
    assert all(item.mention_count <= 2 for item in plan.shards)
    assert plan.trace_payload()["shard_count"] == 2
    assert plan.trace_payload()["input_token_overhead"] == 1_024


def test_convergence_frontier_is_sharded_by_atomic_record_budget() -> None:
    request = EntityConvergenceInput(
        batch_index=0,
        start_chunk_ordinal=0,
        end_chunk_ordinal=9,
        final_batch=False,
        provisional_memory=[
            EntityMemoryRecord(
                memory_id=f"candidate:{index}",
                status="unresolved",
                mention_ids=[f"m{index}"],
                evidence_quotes=[f"人物{index}"],
                last_chunk_ordinal=index,
            )
            for index in range(3)
        ],
        evidence_snippets=["人物0", "人物1", "人物2"],
    )

    plan = plan_convergence_shards(
        request,
        max_records=2,
        max_mentions=100,
        max_input_tokens=100_000,
        max_output_tokens=100_000,
        input_token_overhead=321,
    )

    assert [item.record_count for item in plan.shards] == [2, 1]
    trace = plan.trace_payload()
    assert trace["policy"] == "entity-convergence-shard-v2"
    assert trace["budget"]["max_records"] == 2
    assert trace["max_shard_records"] == 2
    assert trace["input_estimator"] == "serialized_payload_plus_provider_overhead_v1"
    assert trace["input_token_overhead"] == 321

    payload_only = plan_convergence_shards(
        request.model_copy(update={"provisional_memory": request.provisional_memory[:1]}),
        max_records=2,
        max_mentions=100,
        max_input_tokens=100_000,
        max_output_tokens=100_000,
        input_token_overhead=0,
    ).shards[0].estimated_input_tokens
    with pytest.raises(ValueError, match="entity_convergence_record_exceeds_shard_budget"):
        plan_convergence_shards(
            request.model_copy(update={"provisional_memory": request.provisional_memory[:1]}),
            max_records=2,
            max_mentions=100,
            max_input_tokens=payload_only + 320,
            max_output_tokens=100_000,
            input_token_overhead=321,
        )


def test_convergence_single_record_over_budget_fails_closed() -> None:
    request = EntityConvergenceInput(
        batch_index=0,
        start_chunk_ordinal=0,
        end_chunk_ordinal=0,
        final_batch=True,
        provisional_memory=[
            EntityMemoryRecord(
                memory_id="candidate:large",
                status="unresolved",
                mention_ids=["m1", "m2"],
                evidence_quotes=["人物"],
                last_chunk_ordinal=0,
            )
        ],
        evidence_snippets=["人物"],
    )

    with pytest.raises(ValueError, match="entity_convergence_record_exceeds_shard_budget"):
        plan_convergence_shards(
            request,
            max_records=100,
            max_mentions=1,
            max_input_tokens=100_000,
            max_output_tokens=100_000,
        )


def test_provider_coverage_retries_whole_record_after_partial_omission() -> None:
    request = EntityConvergenceInput(
        batch_index=0,
        start_chunk_ordinal=0,
        end_chunk_ordinal=0,
        final_batch=True,
        provisional_memory=[
            EntityMemoryRecord(
                memory_id="candidate:one",
                status="unresolved",
                mention_ids=["m1", "m2"],
                evidence_quotes=["人物甲"],
                last_chunk_ordinal=0,
            ),
            EntityMemoryRecord(
                memory_id="candidate:two",
                status="unresolved",
                mention_ids=["m3"],
                evidence_quotes=["人物乙"],
                last_chunk_ordinal=0,
            ),
        ],
        evidence_snippets=["人物甲", "人物乙"],
    )
    partial = EntityConvergenceResult(
        decisions=[
            EntityConvergenceDecision(
                mention_ids=["m1"],
                action="keep_unresolved",
                evidence_quotes=["人物甲"],
                confidence=0.5,
                rationale="partial record",
            ),
            EntityConvergenceDecision(
                mention_ids=["m3"],
                action="keep_unresolved",
                evidence_quotes=["人物乙"],
                confidence=0.5,
                rationale="complete record",
            ),
        ]
    )

    coverage = analyze_convergence_provider_result(request, partial)

    assert coverage.missing_record_ids == ("candidate:one",)
    assert coverage.omitted_mentions == 1
    assert coverage.uncovered_mentions == 2
    assert [item.mention_ids for item in coverage.accepted_result.decisions] == [["m3"]]
