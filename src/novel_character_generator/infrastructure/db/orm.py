from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class NovelORM(Base, TimestampMixin):
    __tablename__ = "novels"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(300))
    content_sha256: Mapped[str] = mapped_column(String(64), unique=True)
    source_text: Mapped[str] = mapped_column(Text)
    characters: Mapped[list[CharacterORM]] = relationship(back_populates="novel")
    runs: Mapped[list[PipelineRunORM]] = relationship(back_populates="novel")


class CharacterORM(Base, TimestampMixin):
    __tablename__ = "characters"
    __table_args__ = (UniqueConstraint("novel_id", "name"),)

    id: Mapped[UUID] = mapped_column(primary_key=True)
    novel_id: Mapped[UUID] = mapped_column(ForeignKey("novels.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    novel: Mapped[NovelORM] = relationship(back_populates="characters")
    observations: Mapped[list[FeatureObservationORM]] = relationship(back_populates="character")
    images: Mapped[list[GeneratedImageORM]] = relationship(back_populates="character")


class FeatureObservationORM(Base, TimestampMixin):
    __tablename__ = "feature_observations"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    character_id: Mapped[UUID] = mapped_column(ForeignKey("characters.id", ondelete="CASCADE"))
    field_path: Mapped[str] = mapped_column(String(200))
    value: Mapped[str] = mapped_column(Text)
    evidence_quote: Mapped[str] = mapped_column(Text)
    char_start: Mapped[int] = mapped_column(Integer)
    char_end: Mapped[int] = mapped_column(Integer)
    confidence: Mapped[float] = mapped_column(Float)
    character: Mapped[CharacterORM] = relationship(back_populates="observations")


class GeneratedImageORM(Base, TimestampMixin):
    __tablename__ = "generated_images"
    __table_args__ = (UniqueConstraint("provider_request_id"),)

    id: Mapped[UUID] = mapped_column(primary_key=True)
    character_id: Mapped[UUID] = mapped_column(ForeignKey("characters.id", ondelete="CASCADE"))
    artifact_uri: Mapped[str] = mapped_column(Text)
    prompt: Mapped[str] = mapped_column(Text)
    provider_request_id: Mapped[str] = mapped_column(String(200))
    character: Mapped[CharacterORM] = relationship(back_populates="images")


class PipelineRunORM(Base, TimestampMixin):
    __tablename__ = "pipeline_runs"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    novel_id: Mapped[UUID] = mapped_column(ForeignKey("novels.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(30), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(200), unique=True)
    input_payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    result_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    error_code: Mapped[str | None] = mapped_column(String(100))
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    novel: Mapped[NovelORM] = relationship(back_populates="runs")
    steps: Mapped[list[PipelineStepORM]] = relationship(back_populates="run")


class PipelineStepORM(Base, TimestampMixin):
    __tablename__ = "pipeline_steps"
    __table_args__ = (
        UniqueConstraint("run_id", "step_key"),
        Index("ix_pipeline_steps_claim", "status", "next_attempt_at", "lease_expires_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    run_id: Mapped[UUID] = mapped_column(ForeignKey("pipeline_runs.id", ondelete="CASCADE"))
    step_key: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(30))
    attempt: Mapped[int] = mapped_column(Integer, default=0)
    lease_owner: Mapped[str | None] = mapped_column(String(200))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_generation: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    external_request_id: Mapped[str | None] = mapped_column(String(200))
    error_code: Mapped[str | None] = mapped_column(String(100))
    run: Mapped[PipelineRunORM] = relationship(back_populates="steps")
