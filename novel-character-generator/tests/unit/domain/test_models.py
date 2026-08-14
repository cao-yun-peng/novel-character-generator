from uuid import uuid4

import pytest
from pydantic import ValidationError

from novel_character_generator.domain.entities.character import FeatureObservation
from novel_character_generator.domain.entities.evaluation import EvalDataset, GraderVersion
from novel_character_generator.domain.entities.pipeline import PipelineStep, StepStatus
from novel_character_generator.domain.entities.text import MentionSpan
from novel_character_generator.domain.value_objects.temporal import TemporalScope


def test_mention_span_rejects_reversed_offsets() -> None:
    with pytest.raises(ValidationError):
        MentionSpan(
            source_document_version_id=uuid4(),
            source_chunk_id=uuid4(),
            char_start=8,
            char_end=3,
            mention_text="林舟",
            mention_kind="name",
            grounding_status="exact",
            normalization_map_version="v1",
        )


def test_text_observation_requires_temporal_scope() -> None:
    with pytest.raises(ValidationError):
        FeatureObservation(
            character_id=uuid4(),
            field_path="face.eye_color",
            value="black",
            source_kind="text",
            epistemic_status="asserted",
            grounding_status="exact",
            confidence=0.9,
            extraction_run_id=uuid4(),
            extractor_version="mock-v1",
        )


def test_text_observation_accepts_grounded_evidence() -> None:
    timeline_id = uuid4()
    observation = FeatureObservation(
        character_id=uuid4(),
        field_path="hair.color",
        value="black",
        source_kind="text",
        source_document_version_id=uuid4(),
        source_chunk_id=uuid4(),
        evidence_quote="一头黑发",
        char_start=10,
        char_end=14,
        temporal_scope=TemporalScope(timeline_id=timeline_id, scope_type="scene"),
        epistemic_status="asserted",
        grounding_status="exact",
        confidence=0.95,
        extraction_run_id=uuid4(),
        extractor_version="mock-v1",
    )
    assert observation.temporal_scope is not None
    assert observation.temporal_scope.timeline_id == timeline_id


def test_pipeline_step_uses_explicit_transition_rules() -> None:
    step = PipelineStep(run_id=uuid4(), step_key="normalize")
    assert step.can_transition_to(StepStatus.CLAIMED)
    assert not step.can_transition_to(StepStatus.SUCCEEDED)


def test_frozen_eval_dataset_requires_freeze_timestamp() -> None:
    with pytest.raises(ValidationError, match="freeze_state_inconsistent"):
        EvalDataset(
            name="text-golden-set",
            version="v1",
            source="manual",
            split_strategy={"kind": "by_novel"},
            frozen=True,
        )


def test_model_grader_requires_reproducible_provenance() -> None:
    with pytest.raises(ValidationError, match="model_grader_provenance_required"):
        GraderVersion(
            grader_key="semantic-correctness",
            version="v1",
            grader_kind="model",
            definition={"threshold": 0.8},
            rubric_version="rubric-v1",
            content_hash="a" * 64,
        )
