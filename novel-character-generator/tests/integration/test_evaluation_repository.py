from asyncio import to_thread
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from novel_character_generator.domain.entities.evaluation import (
    EvalCase,
    EvalDataset,
    EvalResult,
    EvalRun,
    GraderVersion,
)
from novel_character_generator.infrastructure.db.repositories.evaluation import (
    EvaluationConflict,
    EvaluationRepository,
)


@pytest.mark.asyncio
async def test_evaluation_dataset_isolation_freeze_and_result_uniqueness(
    tmp_path: Path,
) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'evaluation.db'}"
    config = Config("alembic.ini")
    config.cmd_opts = type("Options", (), {"x": [f"database_url={database_url}"]})()
    await to_thread(command.upgrade, config, "head")
    engine = create_async_engine(database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    async with sessions() as session:
        repository = EvaluationRepository(session)
        dataset = EvalDataset(
            name="text-golden-set",
            version="v1",
            source="manual",
            split_strategy={"kind": "by_novel"},
        )
        await repository.create_dataset(dataset)
        case = EvalCase(
            eval_dataset_id=dataset.id,
            dataset_version=dataset.version,
            split_group_key="novel-1",
            split="test",
            task_type="observation",
            expected_output={"hair.color": "black"},
            rubric_version="rubric-v1",
            annotation_status="adjudicated",
        )
        await repository.add_case(case)
        leaked_case = EvalCase(
            eval_dataset_id=dataset.id,
            dataset_version=dataset.version,
            split_group_key="novel-1",
            split="dev",
            task_type="observation",
            expected_output={"hair.color": "black"},
            rubric_version="rubric-v1",
            annotation_status="adjudicated",
        )
        with pytest.raises(EvaluationConflict, match="split_group_leakage"):
            await repository.add_case(leaked_case)

        frozen = await repository.freeze_dataset(dataset.id)
        assert frozen.frozen is True
        with pytest.raises(EvaluationConflict, match="dataset_frozen"):
            await repository.add_case(
                case.model_copy(update={"id": leaked_case.id, "split_group_key": "novel-2"})
            )

        grader = GraderVersion(
            grader_key="exact-match",
            version="v1",
            grader_kind="deterministic",
            definition={"algorithm": "json_exact_match"},
            rubric_version="rubric-v1",
            content_hash="a" * 64,
        )
        await repository.register_grader(grader)
        run = EvalRun(
            eval_dataset_id=dataset.id,
            dataset_version=dataset.version,
            candidate_config_hash="b" * 64,
            grader_bundle_version="bundle-v1",
            random_seeds=[7],
        )
        await repository.create_run(run)
        result = EvalResult(
            eval_run_id=run.id,
            eval_case_id=case.id,
            grader_version_id=grader.id,
            scores={"exact_match": 1.0},
            score=1.0,
            passed=True,
        )
        await repository.record_result(result)
        with pytest.raises(EvaluationConflict, match="already_recorded"):
            await repository.record_result(result.model_copy(update={"id": leaked_case.id}))

    await engine.dispose()
