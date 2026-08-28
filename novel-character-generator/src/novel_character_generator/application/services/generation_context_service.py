from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from novel_character_generator.application.services.appearance_service import (
    AppearanceResolutionError,
    AppearanceService,
    SnapshotTarget,
)
from novel_character_generator.domain.entities.image import GenerationMode
from novel_character_generator.domain.policies.image_rendering import (
    adapt_resolved_character_fields,
    build_scene_render_brief,
    compile_image_render_spec,
)
from novel_character_generator.infrastructure.db.orm import (
    CharacterAppearanceStateORM,
    CharacterConflictORM,
    CharacterORM,
    CharacterRenderProfileORM,
    GenerationContextORM,
    PipelineRunORM,
    PipelineStepORM,
)
from novel_character_generator.infrastructure.db.repositories.run_events import append_run_event

GENERATION_CONTEXT_SCHEMA_VERSION = "generation-context-v2"


def canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def canonical_hash(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


@dataclass(frozen=True)
class ImageRunRequest:
    timeline_id: UUID
    target_event_id: UUID | None = None
    target_scene_id: UUID | None = None
    target_chapter_ordinal: int | None = None
    stage_keys: list[str] = field(default_factory=list)
    candidate_count: int = 1
    generate_character_sheet: bool = False
    generation_mode: GenerationMode = "concept"
    render_overrides: dict[str, object] = field(default_factory=dict)
    budget_limit: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        if self.generation_mode not in {
            "concept",
            "character_design",
            "consistent_scene",
        }:
            raise ValueError("invalid_generation_mode")

    def as_dict(self) -> dict[str, object]:
        return {
            "timeline_id": str(self.timeline_id),
            "target_event_id": str(self.target_event_id) if self.target_event_id else None,
            "target_scene_id": str(self.target_scene_id) if self.target_scene_id else None,
            "target_chapter_ordinal": self.target_chapter_ordinal,
            "stage_keys": list(self.stage_keys),
            "candidate_count": self.candidate_count,
            "generate_character_sheet": self.generate_character_sheet,
            "generation_mode": self.generation_mode,
            "render_overrides": self.render_overrides,
            "budget_limit": str(self.budget_limit),
        }


class GenerationContextBuilder:
    def __init__(
        self,
        session: AsyncSession,
        *,
        provider: str,
        workflow_profile: str,
        workflow_version: str,
    ) -> None:
        self.session = session
        self.provider = provider
        self.workflow_profile = workflow_profile
        self.workflow_version = workflow_version

    async def validate_profile(self, character_id: UUID) -> CharacterRenderProfileORM:
        character = await self.session.get(CharacterORM, character_id)
        if character is None or character.merged_into_character_id is not None:
            raise ValueError("character_not_found")
        profile = await AppearanceService(self.session).latest_profile(character_id)
        if profile is None:
            raise ValueError("render_profile_not_found")
        if profile.record_status != "active":
            raise AppearanceResolutionError("render_profile_stale")
        if profile.status not in {"approved", "locked"}:
            raise AppearanceResolutionError("render_profile_not_approved")
        conflict_id = await self.session.scalar(
            select(CharacterConflictORM.id)
            .where(
                CharacterConflictORM.character_id == character_id,
                CharacterConflictORM.status == "pending",
            )
            .limit(1)
        )
        if conflict_id is not None or profile.unresolved_conflicts:
            raise AppearanceResolutionError("appearance_conflicts_unresolved")
        return profile

    async def freeze(
        self,
        *,
        run: PipelineRunORM,
        character_id: UUID,
        request: ImageRunRequest,
    ) -> GenerationContextORM:
        existing = await self.session.scalar(
            select(GenerationContextORM).where(GenerationContextORM.run_id == run.id)
        )
        if existing is not None:
            return existing
        profile = await self.validate_profile(character_id)
        snapshot = await AppearanceService(self.session).snapshot(
            character_id,
            target=SnapshotTarget(
                timeline_id=request.timeline_id,
                event_id=request.target_event_id,
                scene_id=request.target_scene_id,
                chapter_ordinal=request.target_chapter_ordinal,
            ),
        )
        await self._validate_stage_keys(character_id, snapshot, request.stage_keys)
        scene_brief = build_scene_render_brief(snapshot, request.render_overrides)
        resolved_fields = adapt_resolved_character_fields(snapshot)
        readiness, render_spec = compile_image_render_spec(
            resolved_fields,
            scene_brief,
            generation_mode=request.generation_mode,
            generate_character_sheet=request.generate_character_sheet,
            style_preset=str(snapshot.get("style_preset") or "") or None,
            profile_approved=profile.status in {"approved", "locked"},
            workflow_frozen=bool(self.workflow_profile and self.workflow_version),
        )
        target = {
            "timeline_id": str(request.timeline_id),
            "event_id": str(request.target_event_id) if request.target_event_id else None,
            "scene_id": str(request.target_scene_id) if request.target_scene_id else None,
            "chapter_ordinal": request.target_chapter_ordinal,
            "stage_keys": list(request.stage_keys),
        }
        payload: dict[str, object] = {
            "schema_version": GENERATION_CONTEXT_SCHEMA_VERSION,
            "character_id": str(character_id),
            "render_profile_id": str(profile.id),
            "render_profile_version": profile.version,
            "snapshot": snapshot,
            "resolved_render_fields": resolved_fields.model_dump(mode="json"),
            "target": target,
            "workflow_profile": self.workflow_profile,
            "workflow_version": self.workflow_version,
            "provider": self.provider,
            "candidate_count": request.candidate_count,
            "generate_character_sheet": request.generate_character_sheet,
            "generation_mode": request.generation_mode,
            "scene_render_brief": scene_brief.model_dump(mode="json"),
            "render_readiness": readiness.model_dump(mode="json"),
            "image_render_spec": render_spec.model_dump(mode="json"),
            "budget_limit": str(request.budget_limit),
        }
        context_hash = canonical_hash(payload)
        now = datetime.now(UTC)
        context = GenerationContextORM(
            id=uuid4(),
            run_id=run.id,
            character_id=character_id,
            render_profile_id=profile.id,
            render_profile_version=profile.version,
            snapshot_hash=str(snapshot["snapshot_hash"]),
            context_hash=context_hash,
            workflow_profile=self.workflow_profile,
            workflow_version=self.workflow_version,
            provider=self.provider,
            target=target,
            context_payload=payload,
            candidate_count=request.candidate_count,
            status="frozen",
            created_at=now,
            updated_at=now,
        )
        self.session.add(context)
        await self.session.flush()
        await append_run_event(
            self.session,
            run_id=run.id,
            event_type="generation.context.frozen",
            payload={
                "generation_context_id": str(context.id),
                "context_hash": context.context_hash,
                "snapshot_hash": context.snapshot_hash,
                "profile_version": context.render_profile_version,
                "generation_mode": request.generation_mode,
                "spec_hash": render_spec.spec_hash,
                "concept_ready": readiness.concept_ready,
                "character_design_ready": readiness.character_design_ready,
                "consistent_scene_ready": readiness.consistent_scene_ready,
            },
        )
        return context

    async def _validate_stage_keys(
        self,
        character_id: UUID,
        snapshot: dict[str, object],
        stage_keys: list[str],
    ) -> None:
        if not stage_keys:
            return
        if len(stage_keys) > 1:
            raise AppearanceResolutionError("mock_image_single_stage_only")
        raw_ids = snapshot.get("appearance_state_ids")
        state_ids = [UUID(str(item)) for item in raw_ids] if isinstance(raw_ids, list) else []
        states = list(
            await self.session.scalars(
                select(CharacterAppearanceStateORM).where(
                    CharacterAppearanceStateORM.id.in_(state_ids),
                    CharacterAppearanceStateORM.character_id == character_id,
                )
            )
        )
        requested = stage_keys[0]
        for state in states:
            scope = state.temporal_scope or {}
            candidates = {
                str(state.id),
                state.label or "",
                state.age_stage or "",
                str(scope.get("life_phase_key") or ""),
                str(scope.get("life_phase_label") or ""),
            }
            if requested in candidates:
                return
        raise AppearanceResolutionError("requested_stage_not_resolved")


class ImageRunService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        provider: str,
        workflow_profile: str,
        workflow_version: str,
        candidate_count_max: int,
    ) -> None:
        self.session = session
        self.builder = GenerationContextBuilder(
            session,
            provider=provider,
            workflow_profile=workflow_profile,
            workflow_version=workflow_version,
        )
        self.candidate_count_max = candidate_count_max

    async def create_run(
        self,
        *,
        character_id: UUID,
        request: ImageRunRequest,
        idempotency_key: str,
    ) -> PipelineRunORM:
        if request.candidate_count > self.candidate_count_max:
            raise ValueError("candidate_count_exceeds_provider_limit")
        await self.builder.validate_profile(character_id)
        character = await self.session.get_one(CharacterORM, character_id)
        request_payload = {
            "character_id": str(character_id),
            "provider": self.builder.provider,
            "workflow_profile": self.builder.workflow_profile,
            "workflow_version": self.builder.workflow_version,
            **request.as_dict(),
        }
        request_hash = canonical_hash(request_payload)
        existing = await self.session.scalar(
            select(PipelineRunORM).where(PipelineRunORM.idempotency_key == idempotency_key)
        )
        if existing is not None:
            step = await self.session.scalar(
                select(PipelineStepORM).where(
                    PipelineStepORM.run_id == existing.id,
                    PipelineStepORM.step_key == "freeze_generation_context",
                )
            )
            if (
                existing.run_type != "image_generation"
                or step is None
                or (step.cursor or {}).get("request_hash") != request_hash
            ):
                raise RuntimeError("idempotency_key_payload_conflict")
            return existing
        now = datetime.now(UTC)
        run = PipelineRunORM(
            id=uuid4(),
            novel_id=character.novel_id,
            run_type="image_generation",
            status="queued",
            idempotency_key=idempotency_key,
            cancel_requested=False,
            completed_at=None,
            created_at=now,
            updated_at=now,
        )
        step = PipelineStepORM(
            id=uuid4(),
            run_id=run.id,
            step_key="freeze_generation_context",
            status="queued",
            attempt=0,
            lease_owner=None,
            lease_expires_at=None,
            lease_generation=0,
            heartbeat_at=None,
            next_attempt_at=None,
            cursor={
                "schema_version": "v1",
                "request_hash": request_hash,
                "character_id": str(character_id),
                "request": request.as_dict(),
            },
            error_code=None,
            error_message=None,
            created_at=now,
            updated_at=now,
        )
        self.session.add_all([run, step])
        await self.session.flush()
        await append_run_event(
            self.session,
            run_id=run.id,
            event_type="run.created",
            payload={
                "run_type": run.run_type,
                "step_key": step.step_key,
                "character_id": str(character_id),
                "request_hash": request_hash,
            },
        )
        await self.session.commit()
        return run
