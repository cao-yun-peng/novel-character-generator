from uuid import uuid4

from novel_character_generator.domain.policies.appearance_aggregation import (
    AggregationObservation,
    aggregate_appearance,
)


def observation(
    *,
    field_path: str,
    value: str,
    chapter: int,
    timeline_id: str,
    reality_status: str = "canonical",
) -> AggregationObservation:
    observation_id = uuid4()
    return AggregationObservation(
        id=observation_id,
        fingerprint=f"fingerprint-{observation_id}",
        field_path=field_path,
        value=value,
        temporal_scope={
            "timeline_id": timeline_id,
            "scope_type": "chapter",
            "start_chapter_ordinal": chapter,
            "presentation_mode": "direct",
            "reality_status": reality_status,
        },
        source_kind="text",
        epistemic_status="asserted",
        grounding_status="exact",
        confidence=1.0,
    )


def test_temporal_changes_form_separate_non_overlapping_states() -> None:
    character_id = uuid4()
    document_id = uuid4()
    timeline_id = str(uuid4())
    result = aggregate_appearance(
        character_id=character_id,
        source_document_version_id=document_id,
        observations=[
            observation(
                field_path="hair.color",
                value="black",
                chapter=1,
                timeline_id=timeline_id,
            ),
            observation(
                field_path="hair.color",
                value="white",
                chapter=20,
                timeline_id=timeline_id,
            ),
        ],
        timeline_graph_version="timeline-v1",
    )

    assert len(result.states) == 2
    assert result.conflicts == ()
    assert result.states[0].temporal_scope["end_chapter_ordinal"] == 19
    assert result.states[1].temporal_scope["start_chapter_ordinal"] == 20


def test_same_scope_incompatible_values_create_review_conflict() -> None:
    timeline_id = str(uuid4())
    result = aggregate_appearance(
        character_id=uuid4(),
        source_document_version_id=uuid4(),
        observations=[
            observation(
                field_path="hair.color",
                value="blue",
                chapter=3,
                timeline_id=timeline_id,
            ),
            observation(
                field_path="hair.color",
                value="black",
                chapter=3,
                timeline_id=timeline_id,
            ),
        ],
        timeline_graph_version="timeline-v1",
    )

    assert len(result.states) == 2
    assert len(result.conflicts) == 1
    assert result.conflicts[0].field_path == "hair.color"
    assert set(result.conflicts[0].candidate_values) == {"blue", "black"}


def test_dream_observation_does_not_enter_canonical_identity_anchor() -> None:
    timeline_id = str(uuid4())
    result = aggregate_appearance(
        character_id=uuid4(),
        source_document_version_id=uuid4(),
        observations=[
            observation(
                field_path="face.eye_color",
                value="red",
                chapter=4,
                timeline_id=timeline_id,
                reality_status="subjective",
            )
        ],
        timeline_graph_version="timeline-v1",
    )

    assert result.identity_anchor == {}
    assert result.states[0].temporal_scope["reality_status"] == "subjective"


def test_same_chapter_different_life_phases_do_not_conflict() -> None:
    timeline_id = str(uuid4())
    past_life = observation(
        field_path="age",
        value="29",
        chapter=1,
        timeline_id=timeline_id,
    )
    childhood = observation(
        field_path="age",
        value="六岁",
        chapter=1,
        timeline_id=timeline_id,
    )
    past_life.temporal_scope["life_phase_key"] = "past_life"
    past_life.temporal_scope["life_phase_label"] = "前世"
    childhood.temporal_scope["life_phase_key"] = "reincarnated_childhood"
    childhood.temporal_scope["life_phase_label"] = "转生幼年"

    result = aggregate_appearance(
        character_id=uuid4(),
        source_document_version_id=uuid4(),
        observations=[past_life, childhood],
        timeline_graph_version="timeline-v1",
    )

    assert len(result.states) == 2
    assert result.conflicts == ()
    assert {item.age_stage for item in result.states} == {"前世", "转生幼年"}


def test_transformation_state_is_separate_from_identity_anchor() -> None:
    timeline_id = str(uuid4())
    normal = observation(
        field_path="face.eye_color",
        value="blue",
        chapter=3,
        timeline_id=timeline_id,
    )
    transformed = observation(
        field_path="face.eye_color",
        value="red",
        chapter=3,
        timeline_id=timeline_id,
    )
    transformed.temporal_scope["transformation_state"] = "powered_form"

    result = aggregate_appearance(
        character_id=uuid4(),
        source_document_version_id=uuid4(),
        observations=[normal, transformed],
        timeline_graph_version="timeline-v1",
    )

    assert result.conflicts == ()
    assert result.identity_anchor == {"face": {"eye_color": "blue"}}
    assert {state.state_kind for state in result.states} == {"transformation"}


def test_near_synonym_colors_do_not_create_false_conflict() -> None:
    timeline_id = str(uuid4())
    result = aggregate_appearance(
        character_id=uuid4(),
        source_document_version_id=uuid4(),
        observations=[
            observation(
                field_path="skin.color",
                value="黄色",
                chapter=3,
                timeline_id=timeline_id,
            ),
            observation(
                field_path="skin.color",
                value="暗黄色",
                chapter=3,
                timeline_id=timeline_id,
            ),
        ],
        timeline_graph_version="timeline-v1",
    )

    assert result.conflicts == ()
    assert result.states == ()
    assert result.identity_anchor["skin"]["color"] in {"黄色", "暗黄色"}


def test_multiple_compatible_eye_descriptions_are_combined() -> None:
    timeline_id = str(uuid4())
    result = aggregate_appearance(
        character_id=uuid4(),
        source_document_version_id=uuid4(),
        observations=[
            observation(
                field_path="face.eyes",
                value="眼中带着疲惫",
                chapter=3,
                timeline_id=timeline_id,
            ),
            observation(
                field_path="face.eyes",
                value="目光略显疲倦",
                chapter=3,
                timeline_id=timeline_id,
            ),
        ],
        timeline_graph_version="timeline-v1",
    )

    assert result.conflicts == ()
    assert len(result.states) == 1
    assert result.states[0].appearance["face"]["eyes"] == [
        "眼中带着疲惫",
        "目光略显疲倦",
    ]


def test_multiple_accessories_of_same_type_are_not_a_conflict() -> None:
    timeline_id = str(uuid4())
    result = aggregate_appearance(
        character_id=uuid4(),
        source_document_version_id=uuid4(),
        observations=[
            observation(
                field_path="accessories.badge",
                value="圆形徽章",
                chapter=3,
                timeline_id=timeline_id,
            ),
            observation(
                field_path="accessories.badge",
                value="剑形徽章",
                chapter=3,
                timeline_id=timeline_id,
            ),
        ],
        timeline_graph_version="timeline-v1",
    )

    assert result.conflicts == ()
    assert result.states[0].appearance["accessories"]["badge"] == [
        "剑形徽章",
        "圆形徽章",
    ]
