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
    current_version_id: Mapped[UUID | None] = mapped_column(index=True)
    # Legacy mirror fields retained during the schema transition. New code uses
    # SourceDocumentVersionORM as the immutable content record.
    version: Mapped[str] = mapped_column(String(64))
    sha256: Mapped[str] = mapped_column(String(64), unique=True)
    encoding: Mapped[str] = mapped_column(String(32))
    mime_type: Mapped[str] = mapped_column(String(255))
    storage_uri: Mapped[str] = mapped_column(Text)
    byte_size: Mapped[int] = mapped_column(Integer)
    normalization_map_version: Mapped[str | None] = mapped_column(String(64))
    normalization_map: Mapped[dict[str, Any] | None] = mapped_column(JSON)


class SourceDocumentVersionORM(IdMixin, TimestampMixin, Base):
    __tablename__ = "source_document_versions"
    __table_args__ = (
        UniqueConstraint("source_document_id", "version"),
        Index("ix_source_document_versions_hash", "content_sha256"),
    )

    source_document_id: Mapped[UUID] = mapped_column(
        ForeignKey("source_documents.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[int] = mapped_column(Integer)
    content_sha256: Mapped[str] = mapped_column(String(64))
    encoding: Mapped[str] = mapped_column(String(32))
    mime_type: Mapped[str] = mapped_column(String(255))
    storage_uri: Mapped[str] = mapped_column(Text)
    byte_size: Mapped[int] = mapped_column(Integer)
    normalization_map_id: Mapped[UUID | None] = mapped_column(index=True)
    supersedes_version_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("source_document_versions.id")
    )


class NormalizationMapORM(IdMixin, TimestampMixin, Base):
    __tablename__ = "normalization_maps"

    source_document_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("source_document_versions.id", ondelete="CASCADE"), unique=True
    )
    algorithm_version: Mapped[str] = mapped_column(String(64))
    original_boundaries: Mapped[list[int]] = mapped_column(JSON)


class ChapterORM(IdMixin, Base):
    __tablename__ = "chapters"
    __table_args__ = (
        UniqueConstraint("source_document_version_id", "ordinal"),
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
    source_document_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("source_document_versions.id", ondelete="CASCADE")
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
        UniqueConstraint("source_document_version_id", "ordinal", "content_hash"),
        Index("ix_text_chunks_document_ordinal", "source_document_id", "ordinal"),
        Index("ix_text_chunks_version_ordinal", "source_document_version_id", "ordinal"),
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
    source_document_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("source_document_versions.id", ondelete="CASCADE")
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


class EventParticipantORM(IdMixin, TimestampMixin, Base):
    __tablename__ = "event_participants"
    __table_args__ = (UniqueConstraint("event_id", "character_id", "role"),)

    event_id: Mapped[UUID] = mapped_column(
        ForeignKey("story_events.id", ondelete="CASCADE"), index=True
    )
    character_id: Mapped[UUID] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(32))
    evidence_observation_ids: Mapped[list[str]] = mapped_column(JSON)


class CharacterORM(IdMixin, TimestampMixin, Base):
    __tablename__ = "characters"
    __table_args__ = (
        UniqueConstraint("novel_id", "canonical_name"),
        CheckConstraint("revision >= 1", name="ck_characters_revision_positive"),
    )

    novel_id: Mapped[UUID] = mapped_column(ForeignKey("novels.id", ondelete="CASCADE"), index=True)
    canonical_name: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32))
    revision: Mapped[int] = mapped_column(Integer, default=1)
    merged_into_character_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("characters.id"), index=True
    )


class CharacterEntityOperationORM(IdMixin, TimestampMixin, Base):
    __tablename__ = "character_entity_operations"
    __table_args__ = (
        UniqueConstraint("idempotency_key"),
        Index("ix_character_entity_operations_novel_created", "novel_id", "created_at"),
    )

    operation_type: Mapped[str] = mapped_column(String(32))
    novel_id: Mapped[UUID] = mapped_column(
        ForeignKey("novels.id", ondelete="CASCADE"), index=True
    )
    idempotency_key: Mapped[str] = mapped_column(String(255))
    request_hash: Mapped[str] = mapped_column(String(64))
    source_character_ids: Mapped[list[str]] = mapped_column(JSON)
    target_character_ids: Mapped[list[str]] = mapped_column(JSON)
    action: Mapped[dict[str, Any]] = mapped_column(JSON)
    before_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(32), index=True)
    actor_id: Mapped[str] = mapped_column(String(255))
    reason: Mapped[str] = mapped_column(Text)


class SceneORM(IdMixin, TimestampMixin, Base):
    __tablename__ = "scenes"
    __table_args__ = (
        UniqueConstraint("novel_id", "narrative_order"),
        UniqueConstraint("source_chunk_id", "char_start", "char_end"),
        CheckConstraint("binding_revision >= 1", name="ck_scenes_binding_revision_positive"),
    )

    novel_id: Mapped[UUID] = mapped_column(ForeignKey("novels.id", ondelete="CASCADE"))
    timeline_id: Mapped[UUID] = mapped_column(ForeignKey("timelines.id"))
    event_id: Mapped[UUID | None] = mapped_column(ForeignKey("story_events.id"))
    chapter_ordinal: Mapped[int] = mapped_column(Integer)
    narrative_order: Mapped[int] = mapped_column(Integer)
    point_of_view_character_id: Mapped[UUID | None] = mapped_column(ForeignKey("characters.id"))
    label: Mapped[str | None] = mapped_column(String(500))
    source_document_version_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("source_document_versions.id", ondelete="SET NULL"), index=True
    )
    source_chunk_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("text_chunks.id", ondelete="SET NULL"), index=True
    )
    char_start: Mapped[int | None] = mapped_column(Integer)
    char_end: Mapped[int | None] = mapped_column(Integer)
    presentation_mode: Mapped[str] = mapped_column(String(32))
    reality_status: Mapped[str] = mapped_column(String(32))
    confidence: Mapped[float | None] = mapped_column(Float)
    binding_status: Mapped[str] = mapped_column(String(32), index=True)
    binding_revision: Mapped[int] = mapped_column(Integer, default=1)
    created_by_run_id: Mapped[UUID | None] = mapped_column(ForeignKey("pipeline_runs.id"))


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
    source_document_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("source_document_versions.id", ondelete="CASCADE"), index=True
    )
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
    alias_kind: Mapped[str] = mapped_column(String(32))
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
    source_document_version_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("source_document_versions.id"), index=True
    )
    source_chunk_id: Mapped[UUID | None] = mapped_column(ForeignKey("text_chunks.id"))
    mention_span_id: Mapped[UUID | None] = mapped_column(ForeignKey("mention_spans.id"))
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
    extraction_run_id: Mapped[UUID | None] = mapped_column(ForeignKey("pipeline_runs.id"))
    manual_approval_id: Mapped[UUID | None] = mapped_column(ForeignKey("human_approvals.id"))
    extractor_version: Mapped[str] = mapped_column(String(100))
    supersedes_id: Mapped[UUID | None] = mapped_column(ForeignKey("feature_observations.id"))
    fingerprint: Mapped[str] = mapped_column(String(64), unique=True)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    record_status: Mapped[str] = mapped_column(String(32), default="active")
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    invalidated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    invalidated_by_run_id: Mapped[UUID | None] = mapped_column(ForeignKey("pipeline_runs.id"))


class FeatureSuggestionORM(IdMixin, TimestampMixin, Base):
    __tablename__ = "feature_suggestions"

    character_id: Mapped[UUID] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), index=True
    )
    field_path: Mapped[str] = mapped_column(String(255))
    value: Mapped[Any] = mapped_column(JSON)
    suggestion_kind: Mapped[str] = mapped_column(String(32))
    resource_version: Mapped[str] = mapped_column(String(100))
    confidence: Mapped[float] = mapped_column(Float)
    allowed_fields: Mapped[list[str]] = mapped_column(JSON)
    rationale: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), index=True)
    approval_id: Mapped[UUID | None] = mapped_column(ForeignKey("human_approvals.id"))


class ExpressionObservationORM(IdMixin, TimestampMixin, Base):
    __tablename__ = "expression_observations"
    __table_args__ = (
        CheckConstraint("char_start >= 0", name="ck_expression_observations_start"),
        CheckConstraint("char_end > char_start", name="ck_expression_observations_span"),
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_expression_observations_confidence",
        ),
        UniqueConstraint("fingerprint"),
    )

    character_id: Mapped[UUID] = mapped_column(ForeignKey("characters.id", ondelete="CASCADE"))
    source_document_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("source_document_versions.id"), index=True
    )
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
    fingerprint: Mapped[str] = mapped_column(String(64))


class CharacterAppearanceStateORM(IdMixin, TimestampMixin, Base):
    __tablename__ = "character_appearance_states"
    __table_args__ = (
        Index("ix_appearance_states_character_status", "character_id", "status", "record_status"),
    )

    character_id: Mapped[UUID] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), index=True
    )
    temporal_scope: Mapped[dict[str, Any]] = mapped_column(JSON)
    label: Mapped[str | None] = mapped_column(String(255))
    state_kind: Mapped[str] = mapped_column(String(32), default="base_age_stage")
    merge_priority: Mapped[int] = mapped_column(Integer, default=0)
    age_stage: Mapped[str | None] = mapped_column(String(100))
    appearance: Mapped[dict[str, Any]] = mapped_column(JSON)
    field_sources: Mapped[dict[str, list[str]]] = mapped_column(JSON)
    resolver_version: Mapped[str] = mapped_column(String(100), default="appearance-resolver-v1")
    aggregation_fingerprint: Mapped[str | None] = mapped_column(
        String(64), unique=True, index=True
    )
    created_by_run_id: Mapped[UUID | None] = mapped_column(ForeignKey("pipeline_runs.id"))
    record_status: Mapped[str] = mapped_column(String(32), default="active")
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
    default_stage_key: Mapped[str | None] = mapped_column(String(100))
    appearance_state_ids: Mapped[list[str]] = mapped_column(JSON)
    palette: Mapped[dict[str, Any]] = mapped_column(JSON)
    field_sources: Mapped[dict[str, list[str]]] = mapped_column(JSON)
    field_suggestions: Mapped[dict[str, Any]] = mapped_column(JSON)
    unresolved_conflicts: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    style_preset: Mapped[str] = mapped_column(String(100))
    approved_by: Mapped[str | None] = mapped_column(String(255))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revision: Mapped[int] = mapped_column(Integer)
    record_status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    input_fingerprint: Mapped[str | None] = mapped_column(String(64), index=True)
    source_document_version_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("source_document_versions.id"), index=True
    )
    aggregation_run_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("pipeline_runs.id"), index=True
    )
    aggregation_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSON)


class CharacterConflictORM(IdMixin, TimestampMixin, Base):
    __tablename__ = "character_conflicts"
    __table_args__ = (
        Index("ix_character_conflicts_character_status", "character_id", "status"),
        UniqueConstraint("character_id", "fingerprint"),
        CheckConstraint("revision >= 1", name="ck_character_conflicts_revision_positive"),
    )

    character_id: Mapped[UUID] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), index=True
    )
    field_path: Mapped[str] = mapped_column(String(255))
    appearance_state_ids: Mapped[list[str]] = mapped_column(JSON)
    candidate_values: Mapped[list[Any]] = mapped_column(JSON)
    temporal_scope: Mapped[dict[str, Any]] = mapped_column(JSON)
    merge_priority: Mapped[int] = mapped_column(Integer)
    conflict_kind: Mapped[str] = mapped_column(
        String(32), default="incompatible_values", index=True
    )
    fingerprint: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), default="pending")
    resolution: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    resolved_by: Mapped[str | None] = mapped_column(String(255))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revision: Mapped[int] = mapped_column(Integer, default=1)


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
    run_id: Mapped[UUID] = mapped_column(ForeignKey("pipeline_runs.id"), index=True)
    provider: Mapped[str] = mapped_column(String(100))
    operation_kind: Mapped[str] = mapped_column(String(100))
    idempotency_key: Mapped[str] = mapped_column(String(255))
    request_hash: Mapped[str] = mapped_column(String(64))
    request_fingerprint: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), index=True)
    lease_generation: Mapped[int] = mapped_column(Integer)
    attempt: Mapped[int] = mapped_column(Integer)
    provider_request_id: Mapped[str | None] = mapped_column(String(255), index=True)
    response_hash: Mapped[str | None] = mapped_column(String(64))
    artifact_id: Mapped[UUID | None] = mapped_column(ForeignKey("artifacts.id"))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_reconciled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


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
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    agent_spec_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON)
    tool_spec_versions: Mapped[dict[str, str]] = mapped_column(JSON)
    prompt_version: Mapped[str] = mapped_column(String(100))
    model_policy: Mapped[str] = mapped_column(String(100))
    output_schema: Mapped[str] = mapped_column(String(255))
    permission: Mapped[str] = mapped_column(String(32))
    evaluation_version: Mapped[str | None] = mapped_column(String(100))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_cost: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)


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

    pipeline_run_id: Mapped[UUID | None] = mapped_column(ForeignKey("pipeline_runs.id"))
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

    pipeline_step_id: Mapped[UUID | None] = mapped_column(ForeignKey("pipeline_steps.id"))
    requested_by_agent_run_id: Mapped[UUID | None] = mapped_column(ForeignKey("agent_runs.id"))
    approval_type: Mapped[str] = mapped_column(String(100), index=True)
    subject_type: Mapped[str] = mapped_column(String(100))
    subject_id: Mapped[UUID] = mapped_column(index=True)
    lease_generation: Mapped[int] = mapped_column(Integer)
    revision: Mapped[int] = mapped_column(Integer, default=1)
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
    decision_payload_hash: Mapped[str | None] = mapped_column(String(64))


class AgentEvaluationORM(IdMixin, TimestampMixin, Base):
    __tablename__ = "agent_evaluations"

    agent_run_id: Mapped[UUID] = mapped_column(ForeignKey("agent_runs.id"))
    evaluation_set: Mapped[str] = mapped_column(String(255))
    evaluator_version: Mapped[str] = mapped_column(String(100))
    scores: Mapped[dict[str, Any]] = mapped_column(JSON)
    passed: Mapped[bool] = mapped_column(Boolean)


class EvalDatasetORM(IdMixin, TimestampMixin, Base):
    __tablename__ = "eval_datasets"
    __table_args__ = (UniqueConstraint("name", "version"),)

    name: Mapped[str] = mapped_column(String(255))
    version: Mapped[str] = mapped_column(String(100))
    source: Mapped[str] = mapped_column(String(255))
    split_strategy: Mapped[dict[str, Any]] = mapped_column(JSON)
    dataset_metadata: Mapped[dict[str, Any]] = mapped_column(JSON)
    frozen: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    frozen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EvalCaseORM(IdMixin, TimestampMixin, Base):
    __tablename__ = "eval_cases"
    __table_args__ = (
        Index("ix_eval_cases_dataset_split_task", "eval_dataset_id", "split", "task_type"),
    )

    eval_dataset_id: Mapped[UUID] = mapped_column(
        ForeignKey("eval_datasets.id", ondelete="CASCADE")
    )
    dataset_version: Mapped[str] = mapped_column(String(100))
    source_novel_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("novels.id", ondelete="SET NULL")
    )
    source_document_version_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("source_document_versions.id", ondelete="SET NULL")
    )
    split_group_key: Mapped[str] = mapped_column(String(255), index=True)
    split: Mapped[str] = mapped_column(String(32))
    task_type: Mapped[str] = mapped_column(String(64))
    input_refs: Mapped[list[str]] = mapped_column(JSON)
    expected_output: Mapped[Any] = mapped_column(JSON)
    evidence_spans: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    slice_tags: Mapped[list[str]] = mapped_column(JSON)
    severity: Mapped[str] = mapped_column(String(32))
    rubric_version: Mapped[str] = mapped_column(String(100))
    annotation_status: Mapped[str] = mapped_column(String(32))


class GraderVersionORM(IdMixin, TimestampMixin, Base):
    __tablename__ = "grader_versions"
    __table_args__ = (
        UniqueConstraint("grader_key", "version"),
        UniqueConstraint("content_hash"),
    )

    grader_key: Mapped[str] = mapped_column(String(255))
    version: Mapped[str] = mapped_column(String(100))
    grader_kind: Mapped[str] = mapped_column(String(32))
    definition: Mapped[dict[str, Any]] = mapped_column(JSON)
    model_provider: Mapped[str | None] = mapped_column(String(100))
    model_name: Mapped[str | None] = mapped_column(String(255))
    model_revision: Mapped[str | None] = mapped_column(String(255))
    prompt_version: Mapped[str | None] = mapped_column(String(100))
    rubric_version: Mapped[str] = mapped_column(String(100))
    sampling_parameters: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    content_hash: Mapped[str] = mapped_column(String(64))


class EvalRunORM(IdMixin, TimestampMixin, Base):
    __tablename__ = "eval_runs"

    eval_dataset_id: Mapped[UUID] = mapped_column(ForeignKey("eval_datasets.id"), index=True)
    dataset_version: Mapped[str] = mapped_column(String(100))
    candidate_config_hash: Mapped[str] = mapped_column(String(64))
    baseline_config_hash: Mapped[str | None] = mapped_column(String(64))
    model_versions: Mapped[dict[str, str]] = mapped_column(JSON)
    prompt_versions: Mapped[dict[str, str]] = mapped_column(JSON)
    agent_spec_versions: Mapped[dict[str, str]] = mapped_column(JSON)
    tool_versions: Mapped[dict[str, str]] = mapped_column(JSON)
    schema_versions: Mapped[dict[str, str]] = mapped_column(JSON)
    workflow_profile_version: Mapped[str | None] = mapped_column(String(100))
    grader_bundle_version: Mapped[str] = mapped_column(String(100))
    random_seeds: Mapped[list[int]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(32), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    total_cost: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=0)
    summary: Mapped[dict[str, Any] | None] = mapped_column(JSON)


class EvalResultORM(IdMixin, TimestampMixin, Base):
    __tablename__ = "eval_results"
    __table_args__ = (
        UniqueConstraint("eval_run_id", "eval_case_id", "grader_version_id"),
        CheckConstraint("latency_ms >= 0", name="ck_eval_results_latency_nonnegative"),
        CheckConstraint("input_tokens >= 0", name="ck_eval_results_input_tokens_nonnegative"),
        CheckConstraint("output_tokens >= 0", name="ck_eval_results_output_tokens_nonnegative"),
    )

    eval_run_id: Mapped[UUID] = mapped_column(
        ForeignKey("eval_runs.id", ondelete="CASCADE"), index=True
    )
    eval_case_id: Mapped[UUID] = mapped_column(ForeignKey("eval_cases.id"), index=True)
    grader_version_id: Mapped[UUID] = mapped_column(ForeignKey("grader_versions.id"))
    raw_output_artifact_id: Mapped[UUID | None] = mapped_column(ForeignKey("artifacts.id"))
    scores: Mapped[dict[str, Any]] = mapped_column(JSON)
    score: Mapped[float | None] = mapped_column(Float)
    passed: Mapped[bool] = mapped_column(Boolean)
    diagnostics: Mapped[dict[str, Any]] = mapped_column(JSON)
    failure_reason: Mapped[str | None] = mapped_column(Text)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    cost: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=0)
