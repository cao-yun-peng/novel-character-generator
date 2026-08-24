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
