from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from novel_character_generator.domain.entities.evaluation import (
    EvalCase,
    EvalDataset,
    EvalResult,
    EvalRun,
    GraderVersion,
)
from novel_character_generator.infrastructure.db.orm import (
    EvalCaseORM,
    EvalDatasetORM,
    EvalResultORM,
    EvalRunORM,
    GraderVersionORM,
)


class EvaluationConflict(RuntimeError):
    pass


class EvaluationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_dataset(self, dataset: EvalDataset) -> EvalDatasetORM:
        existing = await self.session.scalar(
            select(EvalDatasetORM).where(
                EvalDatasetORM.name == dataset.name,
                EvalDatasetORM.version == dataset.version,
            )
        )
        if existing is not None:
            raise EvaluationConflict("eval_dataset_version_exists")
        now = datetime.now(UTC)
        row = EvalDatasetORM(
            id=dataset.id,
            name=dataset.name,
            version=dataset.version,
            source=dataset.source,
            split_strategy=dataset.split_strategy,
            dataset_metadata=dataset.metadata,
            frozen=dataset.frozen,
            frozen_at=dataset.frozen_at,
            created_at=now,
            updated_at=now,
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def add_case(self, case: EvalCase) -> EvalCaseORM:
        dataset = await self.session.get(EvalDatasetORM, case.eval_dataset_id)
        if dataset is None:
            raise ValueError("eval_dataset_not_found")
        if dataset.frozen:
            raise EvaluationConflict("eval_dataset_frozen")
        if dataset.version != case.dataset_version:
            raise EvaluationConflict("eval_dataset_version_mismatch")
        leaked_split = await self.session.scalar(
            select(EvalCaseORM.id).where(
                EvalCaseORM.eval_dataset_id == case.eval_dataset_id,
                EvalCaseORM.split_group_key == case.split_group_key,
                EvalCaseORM.split != case.split,
            )
        )
        if leaked_split is not None:
            raise EvaluationConflict("eval_split_group_leakage")
        now = datetime.now(UTC)
        row = EvalCaseORM(
            id=case.id,
            eval_dataset_id=case.eval_dataset_id,
            dataset_version=case.dataset_version,
            source_novel_id=case.source_novel_id,
            source_document_version_id=case.source_document_version_id,
            split_group_key=case.split_group_key,
            split=case.split,
            task_type=case.task_type,
            input_refs=[str(item) for item in case.input_refs],
            expected_output=case.expected_output,
            evidence_spans=[item.model_dump(mode="json") for item in case.evidence_spans],
            slice_tags=case.slice_tags,
            severity=case.severity,
            rubric_version=case.rubric_version,
            annotation_status=case.annotation_status,
            created_at=now,
            updated_at=now,
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def freeze_dataset(self, dataset_id: UUID) -> EvalDatasetORM:
        now = datetime.now(UTC)
        updated_id = await self.session.scalar(
            update(EvalDatasetORM)
            .where(EvalDatasetORM.id == dataset_id, EvalDatasetORM.frozen.is_(False))
            .values(frozen=True, frozen_at=now, updated_at=now)
            .returning(EvalDatasetORM.id)
        )
        if updated_id is None:
            dataset = await self.session.get(EvalDatasetORM, dataset_id)
            if dataset is None:
                raise ValueError("eval_dataset_not_found")
            return dataset
        await self.session.flush()
        return await self.session.get_one(EvalDatasetORM, dataset_id)

    async def register_grader(self, grader: GraderVersion) -> GraderVersionORM:
        now = datetime.now(UTC)
        row = GraderVersionORM(
            id=grader.id,
            grader_key=grader.grader_key,
            version=grader.version,
            grader_kind=grader.grader_kind,
            definition=grader.definition,
            model_provider=grader.model_provider,
            model_name=grader.model_name,
            model_revision=grader.model_revision,
            prompt_version=grader.prompt_version,
            rubric_version=grader.rubric_version,
            sampling_parameters=grader.sampling_parameters,
            content_hash=grader.content_hash,
            created_at=now,
            updated_at=now,
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def create_run(self, run: EvalRun) -> EvalRunORM:
        dataset = await self.session.get(EvalDatasetORM, run.eval_dataset_id)
        if dataset is None:
            raise ValueError("eval_dataset_not_found")
        if not dataset.frozen:
            raise EvaluationConflict("eval_dataset_must_be_frozen")
        if dataset.version != run.dataset_version:
            raise EvaluationConflict("eval_dataset_version_mismatch")
        now = datetime.now(UTC)
        row = EvalRunORM(
            id=run.id,
            eval_dataset_id=run.eval_dataset_id,
            dataset_version=run.dataset_version,
            candidate_config_hash=run.candidate_config_hash,
            baseline_config_hash=run.baseline_config_hash,
            model_versions=run.model_versions,
            prompt_versions=run.prompt_versions,
            agent_spec_versions=run.agent_spec_versions,
            tool_versions=run.tool_versions,
            schema_versions=run.schema_versions,
            workflow_profile_version=run.workflow_profile_version,
            grader_bundle_version=run.grader_bundle_version,
            random_seeds=run.random_seeds,
            status=run.status,
            started_at=run.started_at,
            completed_at=run.completed_at,
            total_tokens=run.total_tokens,
            total_latency_ms=run.total_latency_ms,
            total_cost=run.total_cost,
            summary=None,
            created_at=now,
            updated_at=now,
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def record_result(self, result: EvalResult) -> EvalResultORM:
        run = await self.session.get(EvalRunORM, result.eval_run_id)
        case = await self.session.get(EvalCaseORM, result.eval_case_id)
        grader = await self.session.get(GraderVersionORM, result.grader_version_id)
        if run is None or case is None or grader is None:
            raise ValueError("eval_result_reference_not_found")
        if run.eval_dataset_id != case.eval_dataset_id:
            raise EvaluationConflict("eval_result_dataset_mismatch")
        existing = await self.session.scalar(
            select(EvalResultORM).where(
                EvalResultORM.eval_run_id == result.eval_run_id,
                EvalResultORM.eval_case_id == result.eval_case_id,
                EvalResultORM.grader_version_id == result.grader_version_id,
            )
        )
        if existing is not None:
            raise EvaluationConflict("eval_result_already_recorded")
        now = datetime.now(UTC)
        row = EvalResultORM(
            id=result.id,
            eval_run_id=result.eval_run_id,
            eval_case_id=result.eval_case_id,
            grader_version_id=result.grader_version_id,
            raw_output_artifact_id=result.raw_output_artifact_id,
            scores=result.scores,
            score=result.score,
            passed=result.passed,
            diagnostics=result.diagnostics,
            failure_reason=result.failure_reason,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            latency_ms=result.latency_ms,
            cost=result.cost,
            created_at=now,
            updated_at=now,
        )
        self.session.add(row)
        await self.session.flush()
        return row
