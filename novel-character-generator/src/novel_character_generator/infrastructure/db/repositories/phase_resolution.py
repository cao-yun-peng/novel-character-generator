from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from novel_character_generator.application.ports.phase_resolution import (
    PHASE_RESOLUTION_SCHEMA_VERSION,
    CharacterPhaseResolutionInput,
    CharacterPhaseResolutionResult,
    PhaseObservationInput,
    PhaseSignalInput,
    TemporalSignalKind,
)
from novel_character_generator.domain.policies.visual_fields import (
    transformation_applies_to_visual_fact,
)
from novel_character_generator.infrastructure.db.orm import (
    ChapterORM,
    CharacterLifePhaseORM,
    CharacterPhaseResolutionORM,
    FeatureObservationORM,
    ObservationScopeBindingORM,
    PipelineRunORM,
    TemporalSignalORM,
    TextChunkORM,
    TimelineORM,
)


def _canonical(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _signal_observation_ids(
    signal: TemporalSignalORM,
    observations_by_mention: dict[UUID, list[FeatureObservationORM]],
) -> list[UUID]:
    fact_observation_ids = [UUID(item) for item in signal.feature_observation_ids]
    if fact_observation_ids:
        return list(dict.fromkeys(fact_observation_ids))
    if signal.mention_span_id is None:
        return []
    candidates = observations_by_mention.get(signal.mention_span_id, [])
    if signal.kind == "transformation":
        candidates = [
            item
            for item in candidates
            if item.source_chunk_id == signal.source_chunk_id
            and item.char_start is not None
            and item.char_start >= signal.char_start
            and transformation_applies_to_visual_fact(
                item.field_path,
                item.value,
                item.evidence_quote or "",
            )
        ]
    return list(dict.fromkeys(item.id for item in candidates))


class PhaseResolutionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def canonical_timeline(self, novel_id: UUID) -> TimelineORM:
        timeline = await self.session.scalar(
            select(TimelineORM)
            .where(
                TimelineORM.novel_id == novel_id,
                TimelineORM.canonicality == "canonical",
                TimelineORM.parent_timeline_id.is_(None),
            )
            .order_by(TimelineORM.id)
            .limit(1)
        )
        if timeline is None:
            raise RuntimeError("canonical_timeline_not_found")
        return timeline

    async def affected_character_ids(self, run_id: UUID) -> list[UUID]:
        return sorted(
            set(
                await self.session.scalars(
                    select(FeatureObservationORM.character_id)
                    .where(
                        FeatureObservationORM.extraction_run_id == run_id,
                        FeatureObservationORM.record_status == "pending",
                    )
                    .distinct()
                )
            ),
            key=str,
        )

    async def build_input(
        self,
        *,
        run: PipelineRunORM,
        character_id: UUID,
        timeline_id: UUID,
    ) -> CharacterPhaseResolutionInput:
        observations = list(
            await self.session.scalars(
                select(FeatureObservationORM)
                .where(
                    FeatureObservationORM.extraction_run_id == run.id,
                    FeatureObservationORM.character_id == character_id,
                    FeatureObservationORM.record_status == "pending",
                )
                .order_by(
                    FeatureObservationORM.chapter_ordinal,
                    FeatureObservationORM.char_start,
                    FeatureObservationORM.id,
                )
            )
        )
        observations_by_mention: dict[UUID, list[FeatureObservationORM]] = {}
        for observation in observations:
            if observation.mention_span_id is not None:
                observations_by_mention.setdefault(observation.mention_span_id, []).append(
                    observation
                )

        signals = list(
            await self.session.scalars(
                select(TemporalSignalORM)
                .where(
                    TemporalSignalORM.run_id == run.id,
                    TemporalSignalORM.character_id == character_id,
                    TemporalSignalORM.resolution_status == "bound",
                )
                .order_by(
                    TemporalSignalORM.source_chunk_id,
                    TemporalSignalORM.char_start,
                    TemporalSignalORM.id,
                )
            )
        )
        chapter_by_chunk: dict[UUID, int | None] = {}
        for signal in signals:
            if signal.source_chunk_id in chapter_by_chunk:
                continue
            chunk = await self.session.get(TextChunkORM, signal.source_chunk_id)
            chapter_ordinal: int | None = None
            if chunk is not None and chunk.chapter_id is not None:
                chapter = await self.session.get(ChapterORM, chunk.chapter_id)
                chapter_ordinal = chapter.ordinal if chapter is not None else None
            chapter_by_chunk[signal.source_chunk_id] = chapter_ordinal

        return CharacterPhaseResolutionInput(
            character_id=character_id,
            timeline_id=timeline_id,
            signals=[
                PhaseSignalInput(
                    id=signal.id,
                    kind=cast(TemporalSignalKind, signal.kind),
                    label=signal.label,
                    evidence_quote=signal.evidence_quote,
                    chapter_ordinal=chapter_by_chunk.get(signal.source_chunk_id),
                    confidence=signal.confidence,
                    observation_ids=_signal_observation_ids(
                        signal,
                        observations_by_mention,
                    ),
                )
                for signal in signals
            ],
            observations=[
                PhaseObservationInput(
                    id=observation.id,
                    mention_span_id=observation.mention_span_id,
                    field_path=observation.field_path,
                    chapter_ordinal=observation.chapter_ordinal,
                    confidence=observation.confidence,
                    current_scope=observation.temporal_scope or {},
                )
                for observation in observations
            ],
        )

    async def existing_resolution(
        self, run_id: UUID, character_id: UUID
    ) -> CharacterPhaseResolutionORM | None:
        return cast(
            CharacterPhaseResolutionORM | None,
            await self.session.scalar(
                select(CharacterPhaseResolutionORM).where(
                    CharacterPhaseResolutionORM.run_id == run_id,
                    CharacterPhaseResolutionORM.character_id == character_id,
                )
            ),
        )

    async def materialize(
        self,
        *,
        run: PipelineRunORM,
        source_document_version_id: UUID,
        request: CharacterPhaseResolutionInput,
        result: CharacterPhaseResolutionResult,
    ) -> CharacterPhaseResolutionORM:
        input_hash = _hash(request.model_dump(mode="json"))
        existing_resolution = await self.existing_resolution(run.id, request.character_id)
        if existing_resolution is not None:
            if existing_resolution.input_hash != input_hash:
                raise RuntimeError("phase_resolution_input_changed")
            return existing_resolution

        now = datetime.now(UTC)
        await self.session.execute(
            update(CharacterLifePhaseORM)
            .where(
                CharacterLifePhaseORM.character_id == request.character_id,
                CharacterLifePhaseORM.source_document_version_id == source_document_version_id,
                CharacterLifePhaseORM.record_status == "active",
            )
            .values(record_status="superseded", updated_at=now)
        )
        phase_by_key: dict[str, CharacterLifePhaseORM] = {}
        for phase in result.phases:
            fingerprint = _hash(
                {
                    "character_id": str(request.character_id),
                    "timeline_id": str(request.timeline_id),
                    "phase_key": phase.phase_key,
                    "input_hash": input_hash,
                    "resolver_version": PHASE_RESOLUTION_SCHEMA_VERSION,
                }
            )
            row = await self.session.scalar(
                select(CharacterLifePhaseORM).where(
                    CharacterLifePhaseORM.fingerprint == fingerprint
                )
            )
            if row is None:
                row = CharacterLifePhaseORM(
                    id=uuid4(),
                    run_id=run.id,
                    source_document_version_id=source_document_version_id,
                    character_id=request.character_id,
                    timeline_id=request.timeline_id,
                    phase_key=phase.phase_key,
                    label=phase.label,
                    phase_order=Decimal(phase.phase_order),
                    age_stage=phase.age_stage,
                    start_event_id=None,
                    end_event_id=None,
                    start_chapter_ordinal=phase.start_chapter_ordinal,
                    end_chapter_ordinal=phase.end_chapter_ordinal,
                    evidence_signal_ids=[str(item) for item in phase.evidence_signal_ids],
                    confidence=phase.confidence,
                    status=phase.status,
                    resolver_version=PHASE_RESOLUTION_SCHEMA_VERSION,
                    input_fingerprint=input_hash,
                    fingerprint=fingerprint,
                    revision=1,
                    record_status="active",
                    created_at=now,
                    updated_at=now,
                )
                self.session.add(row)
            phase_by_key[phase.phase_key] = row
        await self.session.flush()

        observations = {
            item.id: item
            for item in await self.session.scalars(
                select(FeatureObservationORM).where(
                    FeatureObservationORM.extraction_run_id == run.id,
                    FeatureObservationORM.character_id == request.character_id,
                    FeatureObservationORM.record_status == "pending",
                )
            )
        }
        for decision in result.scope_decisions:
            observation = observations.get(decision.observation_id)
            if observation is None:
                raise RuntimeError("phase_resolution_observation_missing")
            materialized_phase = (
                phase_by_key.get(decision.phase_key) if decision.phase_key is not None else None
            )
            scope: dict[str, object] = {
                "timeline_id": str(request.timeline_id),
                "scope_type": decision.scope_type,
                "start_chapter_ordinal": decision.start_chapter_ordinal,
                "presentation_mode": decision.presentation_mode,
                "reality_status": decision.reality_status,
                "scope_resolution_status": decision.status,
                "phase_resolver_version": PHASE_RESOLUTION_SCHEMA_VERSION,
            }
            if decision.end_chapter_ordinal is not None:
                scope["end_chapter_ordinal"] = decision.end_chapter_ordinal
            if materialized_phase is not None:
                scope["life_phase_id"] = str(materialized_phase.id)
                scope["life_phase_key"] = materialized_phase.phase_key
                scope["life_phase_label"] = materialized_phase.label
            if decision.transformation_state is not None:
                scope["transformation_state"] = decision.transformation_state
            if decision.reason_codes:
                scope["scope_review_reasons"] = decision.reason_codes

            binding_fingerprint = _hash(
                {
                    "observation_id": str(observation.id),
                    "input_hash": input_hash,
                    "scope": scope,
                    "resolver_version": PHASE_RESOLUTION_SCHEMA_VERSION,
                }
            )
            await self.session.execute(
                update(ObservationScopeBindingORM)
                .where(
                    ObservationScopeBindingORM.observation_id == observation.id,
                    ObservationScopeBindingORM.record_status == "active",
                    ObservationScopeBindingORM.fingerprint != binding_fingerprint,
                )
                .values(record_status="superseded", updated_at=now)
            )
            binding = await self.session.scalar(
                select(ObservationScopeBindingORM).where(
                    ObservationScopeBindingORM.fingerprint == binding_fingerprint
                )
            )
            if binding is None:
                self.session.add(
                    ObservationScopeBindingORM(
                        id=uuid4(),
                        run_id=run.id,
                        observation_id=observation.id,
                        phase_id=(
                            materialized_phase.id if materialized_phase is not None else None
                        ),
                        timeline_id=request.timeline_id,
                        temporal_scope=scope,
                        presentation_mode=decision.presentation_mode,
                        reality_status=decision.reality_status,
                        transformation_state=decision.transformation_state,
                        status=decision.status,
                        confidence=decision.confidence,
                        resolver_version=PHASE_RESOLUTION_SCHEMA_VERSION,
                        input_fingerprint=input_hash,
                        fingerprint=binding_fingerprint,
                        revision=1,
                        record_status="active",
                        created_at=now,
                        updated_at=now,
                    )
                )
            observation.temporal_scope = scope
            observation.updated_at = now

        resolution = CharacterPhaseResolutionORM(
            id=uuid4(),
            run_id=run.id,
            source_document_version_id=source_document_version_id,
            character_id=request.character_id,
            input_hash=input_hash,
            result=result.model_dump(mode="json"),
            resolver_version=PHASE_RESOLUTION_SCHEMA_VERSION,
            status="completed",
            created_at=now,
            updated_at=now,
        )
        self.session.add(resolution)
        await self.session.flush()
        return resolution

    async def mark_unbound_signals_unresolved(self, run_id: UUID) -> None:
        await self.session.execute(
            update(TemporalSignalORM)
            .where(
                TemporalSignalORM.run_id == run_id,
                TemporalSignalORM.character_id.is_(None),
                TemporalSignalORM.resolution_status == "candidate",
            )
            .values(
                resolution_status="unresolved",
                updated_at=datetime.now(UTC),
            )
        )

    async def activate_final_observations(self, run_id: UUID) -> None:
        final_ids = select(ObservationScopeBindingORM.observation_id).where(
            ObservationScopeBindingORM.run_id == run_id,
            ObservationScopeBindingORM.status == "final",
            ObservationScopeBindingORM.record_status == "active",
        )
        now = datetime.now(UTC)
        await self.session.execute(
            update(FeatureObservationORM)
            .where(
                FeatureObservationORM.extraction_run_id == run_id,
                FeatureObservationORM.record_status == "pending",
                FeatureObservationORM.id.in_(final_ids),
            )
            .values(record_status="active", recorded_at=now, updated_at=now)
        )
