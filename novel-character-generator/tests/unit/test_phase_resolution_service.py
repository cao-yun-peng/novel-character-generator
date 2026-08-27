from uuid import UUID

from novel_character_generator.application.ports.phase_resolution import (
    CharacterPhaseResolutionInput,
    PhaseObservationInput,
    PhaseSignalInput,
)
from novel_character_generator.application.services.phase_resolution_service import (
    resolve_character_phases,
)


def _uuid(value: int) -> UUID:
    return UUID(int=value)


def _observation(value: int, chapter: int) -> PhaseObservationInput:
    return PhaseObservationInput(
        id=_uuid(value),
        field_path="hair.color",
        chapter_ordinal=chapter,
        confidence=0.9,
    )


def _signal(
    value: int,
    *,
    kind: str,
    label: str,
    chapter: int,
    observation_id: int,
) -> PhaseSignalInput:
    return PhaseSignalInput.model_validate(
        {
            "id": _uuid(value),
            "kind": kind,
            "label": label,
            "evidence_quote": label,
            "chapter_ordinal": chapter,
            "confidence": 0.95,
            "observation_ids": [_uuid(observation_id)],
        }
    )


def test_resolver_builds_ordered_life_phases_and_assigns_observations() -> None:
    result = resolve_character_phases(
        CharacterPhaseResolutionInput(
            character_id=_uuid(100),
            timeline_id=_uuid(101),
            observations=[_observation(1, 1), _observation(2, 8)],
            signals=[
                _signal(11, kind="life_phase", label="前世", chapter=1, observation_id=1),
                _signal(12, kind="life_phase", label="转世幼年", chapter=8, observation_id=2),
            ],
        )
    )

    assert [phase.phase_key for phase in result.phases] == ["past_life", "reincarnated_childhood"]
    assert result.phases[0].end_chapter_ordinal == 7
    assert [decision.phase_key for decision in result.scope_decisions] == [
        "past_life",
        "reincarnated_childhood",
    ]
    assert all(decision.status == "final" for decision in result.scope_decisions)


def test_resolver_marks_dream_as_subjective_but_final() -> None:
    result = resolve_character_phases(
        CharacterPhaseResolutionInput(
            character_id=_uuid(100),
            timeline_id=_uuid(101),
            observations=[_observation(1, 3)],
            signals=[_signal(11, kind="presentation", label="梦中", chapter=3, observation_id=1)],
        )
    )

    decision = result.scope_decisions[0]
    assert decision.presentation_mode == "dream"
    assert decision.reality_status == "subjective"
    assert decision.status == "final"


def test_resolver_keeps_unscoped_time_jump_pending_for_review() -> None:
    result = resolve_character_phases(
        CharacterPhaseResolutionInput(
            character_id=_uuid(100),
            timeline_id=_uuid(101),
            observations=[_observation(1, 3)],
            signals=[_signal(11, kind="time_jump", label="三年后", chapter=3, observation_id=1)],
        )
    )

    decision = result.scope_decisions[0]
    assert decision.status == "needs_review"
    assert decision.reason_codes == ["unresolved_time_jump"]


def test_resolver_limits_transformation_to_its_chapter() -> None:
    result = resolve_character_phases(
        CharacterPhaseResolutionInput(
            character_id=_uuid(100),
            timeline_id=_uuid(101),
            observations=[_observation(1, 5)],
            signals=[_signal(11, kind="transformation", label="兽化", chapter=5, observation_id=1)],
        )
    )

    decision = result.scope_decisions[0]
    assert decision.scope_type == "chapter"
    assert decision.start_chapter_ordinal == 5
    assert decision.end_chapter_ordinal == 5
    assert decision.transformation_state is not None


def test_resolver_derives_reincarnation_phases_from_grounded_ages() -> None:
    result = resolve_character_phases(
        CharacterPhaseResolutionInput(
            character_id=_uuid(100),
            timeline_id=_uuid(101),
            observations=[_observation(1, 1), _observation(2, 8), _observation(3, 9)],
            signals=[
                _signal(11, kind="age", label="二十九岁", chapter=1, observation_id=1),
                _signal(12, kind="other", label="转生", chapter=8, observation_id=2),
                _signal(13, kind="age", label="六岁", chapter=8, observation_id=2),
            ],
        )
    )

    assert [phase.phase_key for phase in result.phases] == [
        "past_life",
        "reincarnated_childhood",
    ]
    assert [phase.age_stage for phase in result.phases] == ["adulthood", "childhood"]
    assert result.scope_decisions[0].phase_key == "past_life"
    assert result.scope_decisions[1].phase_key == "reincarnated_childhood"
    assert result.scope_decisions[2].phase_key == "reincarnated_childhood"
    assert all(item.status == "final" for item in result.scope_decisions)


def test_resolver_keeps_generic_other_signal_for_review() -> None:
    result = resolve_character_phases(
        CharacterPhaseResolutionInput(
            character_id=_uuid(100),
            timeline_id=_uuid(101),
            observations=[_observation(1, 5)],
            signals=[_signal(11, kind="other", label="特殊姿态", chapter=5, observation_id=1)],
        )
    )

    assert result.scope_decisions[0].status == "needs_review"
    assert result.scope_decisions[0].reason_codes == ["unsupported_special_signal"]


def test_phase_assignment_preserves_each_observation_chapter_start() -> None:
    result = resolve_character_phases(
        CharacterPhaseResolutionInput(
            character_id=_uuid(100),
            timeline_id=_uuid(101),
            observations=[_observation(1, 1), _observation(2, 9)],
            signals=[
                _signal(11, kind="life_phase", label="幼年", chapter=1, observation_id=1)
            ],
        )
    )

    assert result.scope_decisions[0].start_chapter_ordinal == 1
    assert result.scope_decisions[1].phase_key == "childhood"
    assert result.scope_decisions[1].start_chapter_ordinal == 9
