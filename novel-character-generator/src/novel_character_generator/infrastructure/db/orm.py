from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from novel_character_generator.infrastructure.db.base import Base


class IdMixin:
    id: Mapped[UUID] = mapped_column(primary_key=True)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class NovelORM(IdMixin, TimestampMixin, Base):
    __tablename__ = "novels"

    title: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(32), index=True)


class SourceDocumentORM(IdMixin, TimestampMixin, Base):
    __tablename__ = "source_documents"

    novel_id: Mapped[UUID] = mapped_column(ForeignKey("novels.id", ondelete="CASCADE"), index=True)
    version: Mapped[str] = mapped_column(String(64))
    sha256: Mapped[str] = mapped_column(String(64), unique=True)
    encoding: Mapped[str] = mapped_column(String(32))
    mime_type: Mapped[str] = mapped_column(String(255))
    storage_uri: Mapped[str] = mapped_column(Text)
    byte_size: Mapped[int] = mapped_column(Integer)
    normalization_map_version: Mapped[str | None] = mapped_column(String(64))
    normalization_map: Mapped[dict[str, Any] | None] = mapped_column(JSON)


class ChapterORM(IdMixin, Base):
    __tablename__ = "chapters"
    __table_args__ = (
        UniqueConstraint("novel_id", "ordinal"),
        CheckConstraint("ordinal >= 0", name="ck_chapters_ordinal_nonnegative"),
        CheckConstraint(
            "original_char_end > original_char_start",
            name="ck_chapters_original_span",
        ),
        CheckConstraint(
            "normalized_char_end > normalized_char_start",
            name="ck_chapters_normalized_span",
        ),
    )

    novel_id: Mapped[UUID] = mapped_column(ForeignKey("novels.id", ondelete="CASCADE"))
    source_document_id: Mapped[UUID] = mapped_column(
        ForeignKey("source_documents.id", ondelete="CASCADE")
    )
    ordinal: Mapped[int] = mapped_column(Integer)
    title: Mapped[str | None] = mapped_column(String(500))
    original_char_start: Mapped[int] = mapped_column(Integer)
    original_char_end: Mapped[int] = mapped_column(Integer)
    normalized_char_start: Mapped[int] = mapped_column(Integer)
    normalized_char_end: Mapped[int] = mapped_column(Integer)


class TextChunkORM(IdMixin, Base):
    __tablename__ = "text_chunks"
    __table_args__ = (
        UniqueConstraint("novel_id", "ordinal", "content_hash"),
        Index("ix_text_chunks_document_ordinal", "source_document_id", "ordinal"),
        CheckConstraint("ordinal >= 0", name="ck_text_chunks_ordinal_nonnegative"),
        CheckConstraint(
            "original_char_end > original_char_start",
            name="ck_text_chunks_original_span",
        ),
        CheckConstraint(
            "normalized_char_end > normalized_char_start",
            name="ck_text_chunks_normalized_span",
        ),
    )

    novel_id: Mapped[UUID] = mapped_column(ForeignKey("novels.id", ondelete="CASCADE"))
    source_document_id: Mapped[UUID] = mapped_column(
        ForeignKey("source_documents.id", ondelete="CASCADE")
    )
    chapter_id: Mapped[UUID | None] = mapped_column(ForeignKey("chapters.id", ondelete="SET NULL"))
    ordinal: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64))
    original_char_start: Mapped[int] = mapped_column(Integer)
    original_char_end: Mapped[int] = mapped_column(Integer)
    normalized_char_start: Mapped[int] = mapped_column(Integer)
    normalized_char_end: Mapped[int] = mapped_column(Integer)


class TimelineORM(IdMixin, Base):
    __tablename__ = "timelines"

    novel_id: Mapped[UUID] = mapped_column(ForeignKey("novels.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    parent_timeline_id: Mapped[UUID | None] = mapped_column(ForeignKey("timelines.id"))
    branch_event_id: Mapped[UUID | None] = mapped_column(index=True)
    canonicality: Mapped[str] = mapped_column(String(32))


class StoryEventORM(IdMixin, Base):
    __tablename__ = "story_events"

    timeline_id: Mapped[UUID] = mapped_column(
        ForeignKey("timelines.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str | None] = mapped_column(String(500))
    story_order: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CharacterORM(IdMixin, TimestampMixin, Base):
    __tablename__ = "characters"
    __table_args__ = (UniqueConstraint("novel_id", "canonical_name"),)

    novel_id: Mapped[UUID] = mapped_column(ForeignKey("novels.id", ondelete="CASCADE"), index=True)
    canonical_name: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32))


class SceneORM(IdMixin, Base):
    __tablename__ = "scenes"
    __table_args__ = (UniqueConstraint("novel_id", "narrative_order"),)

    novel_id: Mapped[UUID] = mapped_column(ForeignKey("novels.id", ondelete="CASCADE"))
    timeline_id: Mapped[UUID] = mapped_column(ForeignKey("timelines.id"))
    event_id: Mapped[UUID | None] = mapped_column(ForeignKey("story_events.id"))
    chapter_ordinal: Mapped[int] = mapped_column(Integer)
    narrative_order: Mapped[int] = mapped_column(Integer)
    point_of_view_character_id: Mapped[UUID | None] = mapped_column(ForeignKey("characters.id"))


class PipelineRunORM(IdMixin, TimestampMixin, Base):
    __tablename__ = "pipeline_runs"

    novel_id: Mapped[UUID] = mapped_column(ForeignKey("novels.id", ondelete="CASCADE"), index=True)
    run_type: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(255), unique=True)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PipelineStepORM(IdMixin, TimestampMixin, Base):
    __tablename__ = "pipeline_steps"
    __table_args__ = (
        UniqueConstraint("run_id", "step_key"),
        Index("ix_pipeline_steps_claim", "status", "lease_expires_at"),
        CheckConstraint("attempt >= 0", name="ck_pipeline_steps_attempt_nonnegative"),
        CheckConstraint("lease_generation >= 0", name="ck_pipeline_steps_generation_nonnegative"),
    )

    run_id: Mapped[UUID] = mapped_column(ForeignKey("pipeline_runs.id", ondelete="CASCADE"))
    step_key: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(32))
    attempt: Mapped[int] = mapped_column(Integer, default=0)
    lease_owner: Mapped[str | None] = mapped_column(String(255))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_generation: Mapped[int] = mapped_column(Integer, default=0)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cursor: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    error_code: Mapped[str | None] = mapped_column(String(100))
    error_message: Mapped[str | None] = mapped_column(Text)


class RunEventORM(IdMixin, Base):
    __tablename__ = "run_events"
    __table_args__ = (UniqueConstraint("run_id", "sequence"),)

    run_id: Mapped[UUID] = mapped_column(ForeignKey("pipeline_runs.id", ondelete="CASCADE"))
    sequence: Mapped[int] = mapped_column(Integer)
    event_type: Mapped[str] = mapped_column(String(100))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class MentionSpanORM(IdMixin, TimestampMixin, Base):
    __tablename__ = "mention_spans"
    __table_args__ = (
        CheckConstraint("char_start >= 0", name="ck_mention_spans_start_nonnegative"),
        CheckConstraint("char_end > char_start", name="ck_mention_spans_valid_span"),
    )

    source_document_version: Mapped[str] = mapped_column(String(64))
    source_chunk_id: Mapped[UUID] = mapped_column(ForeignKey("text_chunks.id", ondelete="CASCADE"))
    char_start: Mapped[int] = mapped_column(Integer)
    char_end: Mapped[int] = mapped_column(Integer)
    mention_text: Mapped[str] = mapped_column(Text)
    mention_kind: Mapped[str] = mapped_column(String(32))
    candidate_character_ids: Mapped[list[str]] = mapped_column(JSON)
    resolved_character_id: Mapped[UUID | None] = mapped_column(ForeignKey("characters.id"))
    grounding_status: Mapped[str] = mapped_column(String(32))
    normalization_map_version: Mapped[str] = mapped_column(String(64))


class AliasAssertionORM(IdMixin, TimestampMixin, Base):
    __tablename__ = "alias_assertions"
    __table_args__ = (Index("ix_alias_assertions_normalized", "normalized_alias"),)

    alias_text: Mapped[str] = mapped_column(String(255))
    normalized_alias: Mapped[str] = mapped_column(String(255))
    mention_span_id: Mapped[UUID] = mapped_column(ForeignKey("mention_spans.id"))
    proposed_character_id: Mapped[UUID | None] = mapped_column(ForeignKey("characters.id"))
    speaker_id: Mapped[UUID | None] = mapped_column(ForeignKey("characters.id"))
    scene_id: Mapped[UUID | None] = mapped_column(ForeignKey("scenes.id"))
    timeline_id: Mapped[UUID | None] = mapped_column(ForeignKey("timelines.id"))
    supporting_evidence_ids: Mapped[list[str]] = mapped_column(JSON)
    opposing_evidence_ids: Mapped[list[str]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(32))


class FeatureObservationORM(IdMixin, TimestampMixin, Base):
    __tablename__ = "feature_observations"
    __table_args__ = (
        Index("ix_feature_observations_character_field", "character_id", "field_path"),
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_feature_observations_confidence",
        ),
        CheckConstraint(
            "(char_start IS NULL AND char_end IS NULL) OR "
            "(char_start >= 0 AND char_end > char_start)",
            name="ck_feature_observations_span",
        ),
    )

    character_id: Mapped[UUID] = mapped_column(ForeignKey("characters.id", ondelete="CASCADE"))
    field_path: Mapped[str] = mapped_column(String(255))
    value: Mapped[Any] = mapped_column(JSON)
    source_kind: Mapped[str] = mapped_column(String(32))
    source_chunk_id: Mapped[UUID | None] = mapped_column(ForeignKey("text_chunks.id"))
    evidence_quote: Mapped[str | None] = mapped_column(Text)
    char_start: Mapped[int | None] = mapped_column(Integer)
    char_end: Mapped[int | None] = mapped_column(Integer)
    chapter_ordinal: Mapped[int | None] = mapped_column(Integer)
    scene_id: Mapped[UUID | None] = mapped_column(ForeignKey("scenes.id"))
    event_id: Mapped[UUID | None] = mapped_column(ForeignKey("story_events.id"))
    temporal_scope: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    epistemic_status: Mapped[str] = mapped_column(String(32))
    grounding_status: Mapped[str] = mapped_column(String(32))
    confidence: Mapped[float] = mapped_column(Float)
    extraction_run_id: Mapped[UUID] = mapped_column(ForeignKey("pipeline_runs.id"))
    extractor_version: Mapped[str] = mapped_column(String(100))
    supersedes_id: Mapped[UUID | None] = mapped_column(ForeignKey("feature_observations.id"))
    fingerprint: Mapped[str] = mapped_column(String(64), unique=True)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ExpressionObservationORM(IdMixin, TimestampMixin, Base):
    __tablename__ = "expression_observations"
    __table_args__ = (
        CheckConstraint("char_start >= 0", name="ck_expression_observations_start"),
        CheckConstraint("char_end > char_start", name="ck_expression_observations_span"),
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_expression_observations_confidence",
        ),
    )

    character_id: Mapped[UUID] = mapped_column(ForeignKey("characters.id", ondelete="CASCADE"))
    source_chunk_id: Mapped[UUID] = mapped_column(ForeignKey("text_chunks.id"))
    char_start: Mapped[int] = mapped_column(Integer)
    char_end: Mapped[int] = mapped_column(Integer)
    outward_emotion: Mapped[str] = mapped_column(String(32))
    expression_text: Mapped[str | None] = mapped_column(String(500))
    visible_cues: Mapped[list[str]] = mapped_column(JSON)
    intensity: Mapped[float | None] = mapped_column(Float)
    valence: Mapped[float | None] = mapped_column(Float)
    arousal: Mapped[float | None] = mapped_column(Float)
    is_masked: Mapped[bool | None] = mapped_column(Boolean)
    internal_emotion: Mapped[str | None] = mapped_column(String(255))
    target_character_id: Mapped[UUID | None] = mapped_column(ForeignKey("characters.id"))
    cause_event_id: Mapped[UUID | None] = mapped_column(ForeignKey("story_events.id"))
    scene_id: Mapped[UUID | None] = mapped_column(ForeignKey("scenes.id"))
    temporal_scope: Mapped[dict[str, Any]] = mapped_column(JSON)
    evidence_quote: Mapped[str] = mapped_column(Text)
    epistemic_status: Mapped[str] = mapped_column(String(32))
    confidence: Mapped[float] = mapped_column(Float)
    extraction_run_id: Mapped[UUID] = mapped_column(ForeignKey("pipeline_runs.id"))
    extractor_version: Mapped[str] = mapped_column(String(100))


class CharacterAppearanceStateORM(IdMixin, TimestampMixin, Base):
    __tablename__ = "character_appearance_states"

    character_id: Mapped[UUID] = mapped_column(ForeignKey("characters.id", ondelete="CASCADE"))
    temporal_scope: Mapped[dict[str, Any]] = mapped_column(JSON)
    label: Mapped[str | None] = mapped_column(String(255))
    age_stage: Mapped[str | None] = mapped_column(String(100))
    appearance: Mapped[dict[str, Any]] = mapped_column(JSON)
    field_sources: Mapped[dict[str, list[str]]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(32))


class CharacterRenderProfileORM(IdMixin, TimestampMixin, Base):
    __tablename__ = "character_render_profiles"
    __table_args__ = (UniqueConstraint("character_id", "version"),)

    character_id: Mapped[UUID] = mapped_column(ForeignKey("characters.id", ondelete="CASCADE"))
    version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32))
    identity_anchor: Mapped[dict[str, Any]] = mapped_column(JSON)
    default_appearance_state_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("character_appearance_states.id")
    )
    appearance_state_ids: Mapped[list[str]] = mapped_column(JSON)
    palette: Mapped[dict[str, Any]] = mapped_column(JSON)
    field_sources: Mapped[dict[str, list[str]]] = mapped_column(JSON)
    unresolved_conflicts: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    style_preset: Mapped[str] = mapped_column(String(100))
    approved_by: Mapped[str | None] = mapped_column(String(255))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revision: Mapped[int] = mapped_column(Integer)


class CharacterImageSetORM(IdMixin, TimestampMixin, Base):
    __tablename__ = "character_image_sets"
    __table_args__ = (UniqueConstraint("character_id", "version"),)

    character_id: Mapped[UUID] = mapped_column(ForeignKey("characters.id", ondelete="CASCADE"))
    render_profile_id: Mapped[UUID] = mapped_column(ForeignKey("character_render_profiles.id"))
    render_profile_version: Mapped[int] = mapped_column(Integer)
    version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32))
    default_representative_image_id: Mapped[UUID | None] = mapped_column(index=True)
    stage_image_ids: Mapped[list[str]] = mapped_column(JSON)
    selection_policy_version: Mapped[str] = mapped_column(String(100))


class GeneratedImageORM(IdMixin, TimestampMixin, Base):
    __tablename__ = "generated_images"

    character_id: Mapped[UUID] = mapped_column(ForeignKey("characters.id"))
    run_id: Mapped[UUID] = mapped_column(ForeignKey("pipeline_runs.id"))
    artifact_id: Mapped[UUID] = mapped_column(ForeignKey("artifacts.id"))
    workflow_profile: Mapped[str] = mapped_column(String(100))
    workflow_version: Mapped[str] = mapped_column(String(100))
    snapshot_hash: Mapped[str] = mapped_column(String(64))
    evaluation: Mapped[dict[str, Any] | None] = mapped_column(JSON)


class CharacterStageImageORM(IdMixin, TimestampMixin, Base):
    __tablename__ = "character_stage_images"
    __table_args__ = (UniqueConstraint("image_set_id", "appearance_state_id"),)

    image_set_id: Mapped[UUID] = mapped_column(
        ForeignKey("character_image_sets.id", ondelete="CASCADE")
    )
    appearance_state_id: Mapped[UUID] = mapped_column(ForeignKey("character_appearance_states.id"))
    resolved_snapshot_hash: Mapped[str] = mapped_column(String(64))
    stage_label: Mapped[str] = mapped_column(String(255))
    representative_event_id: Mapped[UUID | None] = mapped_column(ForeignKey("story_events.id"))
    candidate_image_ids: Mapped[list[str]] = mapped_column(JSON)
    baseline_image_id: Mapped[UUID | None] = mapped_column(ForeignKey("generated_images.id"))
    display_order: Mapped[int] = mapped_column(Integer)
    selection_reason_codes: Mapped[list[str]] = mapped_column(JSON)


class ArtifactORM(IdMixin, TimestampMixin, Base):
    __tablename__ = "artifacts"

    content_hash: Mapped[str] = mapped_column(String(64), unique=True)
    mime_type: Mapped[str] = mapped_column(String(255))
    storage_uri: Mapped[str] = mapped_column(Text)
    byte_size: Mapped[int] = mapped_column(Integer)
    artifact_kind: Mapped[str] = mapped_column(String(64))


class ExternalOperationORM(IdMixin, TimestampMixin, Base):
    __tablename__ = "external_operations"
    __table_args__ = (UniqueConstraint("provider", "idempotency_key"),)

    pipeline_step_id: Mapped[UUID] = mapped_column(ForeignKey("pipeline_steps.id"))
    provider: Mapped[str] = mapped_column(String(100))
    operation_kind: Mapped[str] = mapped_column(String(100))
    idempotency_key: Mapped[str] = mapped_column(String(255))
    request_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), index=True)
    provider_request_id: Mapped[str | None] = mapped_column(String(255), index=True)
    response_hash: Mapped[str | None] = mapped_column(String(64))
    artifact_id: Mapped[UUID | None] = mapped_column(ForeignKey("artifacts.id"))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ModelCallORM(IdMixin, TimestampMixin, Base):
    __tablename__ = "model_calls"

    pipeline_step_id: Mapped[UUID] = mapped_column(ForeignKey("pipeline_steps.id"))
    provider: Mapped[str] = mapped_column(String(100))
    model: Mapped[str] = mapped_column(String(255))
    model_revision: Mapped[str | None] = mapped_column(String(255))
    request_hash: Mapped[str] = mapped_column(String(64))
    response_hash: Mapped[str | None] = mapped_column(String(64))
    provider_request_id: Mapped[str | None] = mapped_column(String(255))
    usage: Mapped[dict[str, Any]] = mapped_column(JSON)
    pricing_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    finish_reason: Mapped[str | None] = mapped_column(String(100))


class AgentRunORM(IdMixin, TimestampMixin, Base):
    __tablename__ = "agent_runs"

    pipeline_step_id: Mapped[UUID] = mapped_column(ForeignKey("pipeline_steps.id"))
    agent_id: Mapped[str] = mapped_column(String(100))
    agent_version: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(32))
    budget: Mapped[dict[str, Any]] = mapped_column(JSON)
    context_hash: Mapped[str] = mapped_column(String(64))
    final_output_hash: Mapped[str | None] = mapped_column(String(64))
    stop_reason: Mapped[str | None] = mapped_column(String(100))


class AgentTurnORM(IdMixin, TimestampMixin, Base):
    __tablename__ = "agent_turns"
    __table_args__ = (UniqueConstraint("agent_run_id", "turn_number"),)

    agent_run_id: Mapped[UUID] = mapped_column(ForeignKey("agent_runs.id", ondelete="CASCADE"))
    turn_number: Mapped[int] = mapped_column(Integer)
    input_context_hash: Mapped[str] = mapped_column(String(64))
    output_summary: Mapped[dict[str, Any]] = mapped_column(JSON)
    usage: Mapped[dict[str, Any]] = mapped_column(JSON)


class ToolCallORM(IdMixin, TimestampMixin, Base):
    __tablename__ = "tool_calls"
    __table_args__ = (UniqueConstraint("call_id"),)

    agent_run_id: Mapped[UUID] = mapped_column(ForeignKey("agent_runs.id", ondelete="CASCADE"))
    call_id: Mapped[str] = mapped_column(String(255))
    tool_name: Mapped[str] = mapped_column(String(255))
    tool_version: Mapped[str] = mapped_column(String(100))
    input_hash: Mapped[str] = mapped_column(String(64))
    output_hash: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32))
    side_effect: Mapped[bool] = mapped_column(Boolean)
    duration_ms: Mapped[int] = mapped_column(Integer)
    error_code: Mapped[str | None] = mapped_column(String(100))


class DecisionRecordORM(IdMixin, TimestampMixin, Base):
    __tablename__ = "decision_records"

    pipeline_run_id: Mapped[UUID] = mapped_column(ForeignKey("pipeline_runs.id"))
    agent_run_id: Mapped[UUID | None] = mapped_column(ForeignKey("agent_runs.id"))
    decision_kind: Mapped[str] = mapped_column(String(100))
    subject_type: Mapped[str] = mapped_column(String(100))
    subject_id: Mapped[UUID] = mapped_column(index=True)
    decision: Mapped[dict[str, Any]] = mapped_column(JSON)
    evidence_ids: Mapped[list[str]] = mapped_column(JSON)
    source_kind: Mapped[str] = mapped_column(String(32))


class HumanApprovalORM(IdMixin, TimestampMixin, Base):
    __tablename__ = "human_approvals"
    __table_args__ = (UniqueConstraint("action_hash"),)

    pipeline_step_id: Mapped[UUID] = mapped_column(ForeignKey("pipeline_steps.id"))
    action_hash: Mapped[str] = mapped_column(String(64))
    action: Mapped[dict[str, Any]] = mapped_column(JSON)
    supporting_evidence_ids: Mapped[list[str]] = mapped_column(JSON)
    opposing_evidence_ids: Mapped[list[str]] = mapped_column(JSON)
    estimated_cost: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(32), index=True)
    decision: Mapped[str | None] = mapped_column(String(32))
    modifications: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    resolved_by: Mapped[str | None] = mapped_column(String(255))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    recovery_token_hash: Mapped[str] = mapped_column(String(64), unique=True)


class AgentEvaluationORM(IdMixin, TimestampMixin, Base):
    __tablename__ = "agent_evaluations"

    agent_run_id: Mapped[UUID] = mapped_column(ForeignKey("agent_runs.id"))
    evaluation_set: Mapped[str] = mapped_column(String(255))
    evaluator_version: Mapped[str] = mapped_column(String(100))
    scores: Mapped[dict[str, Any]] = mapped_column(JSON)
    passed: Mapped[bool] = mapped_column(Boolean)
