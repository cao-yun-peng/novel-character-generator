from asyncio import to_thread
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from novel_character_generator.application.ports.entity_resolution import (
    EntityConvergenceDecision,
    EntityConvergenceInput,
    EntityConvergenceResult,
    EntityMentionDecision,
    EntityResolutionInput,
    EntityResolutionResult,
)
from novel_character_generator.application.ports.extraction import (
    VisualCandidateExtractionResult,
    VisualEntityCandidate,
    VisualFactCandidate,
)
from novel_character_generator.application.services.ingestion_service import IngestionService
from novel_character_generator.infrastructure.db.orm import (
    CharacterConvergenceBatchORM,
    CharacterORM,
    FeatureObservationORM,
    MentionSpanORM,
    RunEventORM,
)
from novel_character_generator.infrastructure.llm.mock import MockEntityResolutionProvider
from novel_character_generator.infrastructure.storage.local import LocalArtifactStore
from novel_character_generator.workers.handlers.extraction import process_extraction_run
from novel_character_generator.workers.handlers.ingestion import process_ingestion_run


class ElevenChapterVisualProvider:
    version = "eleven-chapter-visual-v1"

    async def extract_chunk(self, text: str) -> VisualCandidateExtractionResult:
        assert "唐三" in text and "黑发" in text
        return VisualCandidateExtractionResult(
            entities=[
                VisualEntityCandidate(
                    local_id="e1",
                    representative_name="唐三",
                    mention_quote="唐三",
                    mention_kind="name",
                    confidence=1.0,
                )
            ],
            visual_candidates=[
                VisualFactCandidate(
                    entity_ref="e1",
                    field_path="hair.color",
                    value="黑色",
                    evidence_quote="黑发",
                    confidence=1.0,
                )
            ],
        )


class RecordingResolver:
    version = "recording-resolver-v1"

    def __init__(self) -> None:
        self.delegate = MockEntityResolutionProvider()
        self.resolution_inputs: list[EntityResolutionInput] = []
        self.convergence_inputs: list[EntityConvergenceInput] = []

    async def resolve_chunk(self, request: EntityResolutionInput) -> EntityResolutionResult:
        self.resolution_inputs.append(request)
        return await self.delegate.resolve_chunk(request)

    async def converge_batch(
        self, request: EntityConvergenceInput
    ) -> EntityConvergenceResult:
        self.convergence_inputs.append(request)
        return await self.delegate.converge_batch(request)


class AmbiguousBoyVisualProvider:
    version = "ambiguous-boy-visual-v1"

    async def extract_chunk(self, text: str) -> VisualCandidateExtractionResult:
        if "正是唐三" in text:
            return VisualCandidateExtractionResult(
                entities=[
                    VisualEntityCandidate(
                        local_id="named",
                        representative_name="唐三",
                        mention_quote="唐三",
                        mention_kind="name",
                        confidence=1.0,
                    )
                ]
            )
        value = "黑色" if "黑发" in text else "红色"
        quote = "黑发" if "黑发" in text else "红衣"
        return VisualCandidateExtractionResult(
            entities=[
                VisualEntityCandidate(
                    local_id="boy",
                    representative_name="男孩",
                    mention_quote="男孩",
                    mention_kind="title",
                    confidence=1.0,
                )
            ],
            visual_candidates=[
                VisualFactCandidate(
                    entity_ref="boy",
                    field_path=("hair.color" if quote == "黑发" else "clothing.color"),
                    value=value,
                    evidence_quote=quote,
                    confidence=1.0,
                )
            ],
        )


class AmbiguousBoyResolver:
    version = "ambiguous-boy-resolver-v1"

    async def resolve_chunk(self, request: EntityResolutionInput) -> EntityResolutionResult:
        mention_id = request.candidates.mentions[0].mention_id
        if request.chunk_ordinal == 0:
            return EntityResolutionResult(
                decisions=[
                    EntityMentionDecision(
                        mention_id=mention_id,
                        action="create_candidate",
                        evidence_quotes=["男孩"],
                        confidence=0.8,
                        rationale="first local description",
                    )
                ]
            )
        if request.chunk_ordinal == 1:
            prior = next(
                item for item in request.cumulative_memory if "男孩" in item.names
            )
            return EntityResolutionResult(
                decisions=[
                    EntityMentionDecision(
                        mention_id=mention_id,
                        action="link_existing",
                        target_memory_id=prior.memory_id,
                        related_mention_ids=prior.mention_ids,
                        evidence_quotes=["这个男孩正是唐三"],
                        confidence=0.99,
                        rationale="explicit identity statement",
                    )
                ]
            )
        return EntityResolutionResult(
            decisions=[
                EntityMentionDecision(
                    mention_id=mention_id,
                    action="unresolved",
                    evidence_quotes=["男孩"],
                    confidence=0.7,
                    rationale="generic label alone does not prove identity",
                )
            ]
        )

    async def converge_batch(
        self, request: EntityConvergenceInput
    ) -> EntityConvergenceResult:
        identified = next(
            item for item in request.provisional_memory if "唐三" in item.names
        )
        unresolved = next(
            item
            for item in request.provisional_memory
            if item.memory_id != identified.memory_id
        )
        return EntityConvergenceResult(
            decisions=[
                EntityConvergenceDecision(
                    mention_ids=identified.mention_ids,
                    action="create_character",
                    canonical_name="唐三",
                    creation_key="tang-san",
                    evidence_quotes=["这个男孩正是唐三"],
                    confidence=0.99,
                    rationale="explicit cross-chapter identity",
                ),
                EntityConvergenceDecision(
                    mention_ids=unresolved.mention_ids,
                    action="keep_unresolved",
                    evidence_quotes=["男孩"],
                    confidence=0.7,
                    rationale="the later generic mention lacks identity evidence",
                ),
            ]
        )


class FrontierVisualProvider:
    version = "frontier-visual-v1"

    async def extract_chunk(self, text: str) -> VisualCandidateExtractionResult:
        name = "旧人" if "旧人" in text else "新人" if "新人" in text else None
        if name is None:
            return VisualCandidateExtractionResult()
        return VisualCandidateExtractionResult(
            entities=[
                VisualEntityCandidate(
                    local_id="person",
                    representative_name=name,
                    mention_quote=name,
                    mention_kind="title",
                    confidence=1.0,
                )
            ]
        )


class FrontierResolver:
    version = "frontier-resolver-v1"

    def __init__(self) -> None:
        self.convergence_inputs: list[EntityConvergenceInput] = []

    async def resolve_chunk(self, request: EntityResolutionInput) -> EntityResolutionResult:
        mention = request.candidates.mentions[0]
        return EntityResolutionResult(
            decisions=[
                EntityMentionDecision(
                    mention_id=mention.mention_id,
                    action="unresolved",
                    evidence_quotes=[mention.mention_text],
                    confidence=0.5,
                    rationale="title alone is insufficient",
                )
            ]
        )

    async def converge_batch(
        self, request: EntityConvergenceInput
    ) -> EntityConvergenceResult:
        self.convergence_inputs.append(request)
        return EntityConvergenceResult(
            decisions=[
                EntityConvergenceDecision(
                    mention_ids=record.mention_ids,
                    action="keep_unresolved",
                    evidence_quotes=[record.evidence_quotes[-1]],
                    confidence=0.5,
                    rationale="no new identity evidence",
                )
                for record in request.provisional_memory
            ]
        )


class ThreePersonVisualProvider:
    version = "three-person-visual-v1"

    async def extract_chunk(self, text: str) -> VisualCandidateExtractionResult:
        return VisualCandidateExtractionResult(
            entities=[
                VisualEntityCandidate(
                    local_id=f"person-{index}",
                    representative_name=name,
                    mention_quote=name,
                    mention_kind="title",
                    confidence=1.0,
                )
                for index, name in enumerate(("甲客", "乙客", "丙客"))
            ]
        )


class RepairingShardResolver:
    version = "repairing-shard-resolver-v1"

    def __init__(self, *, always_omit: bool = False) -> None:
        self.always_omit = always_omit
        self.convergence_inputs: list[EntityConvergenceInput] = []

    async def resolve_chunk(self, request: EntityResolutionInput) -> EntityResolutionResult:
        return EntityResolutionResult(
            decisions=[
                EntityMentionDecision(
                    mention_id=mention.mention_id,
                    action="unresolved",
                    evidence_quotes=[mention.mention_text],
                    confidence=0.5,
                    rationale="local title remains unresolved",
                )
                for mention in request.candidates.mentions
            ]
        )

    async def converge_batch(
        self, request: EntityConvergenceInput
    ) -> EntityConvergenceResult:
        self.convergence_inputs.append(request)
        records = list(request.provisional_memory)
        if self.always_omit:
            records = []
        elif len(self.convergence_inputs) == 1:
            records = records[:-1]
        return EntityConvergenceResult(
            decisions=[
                EntityConvergenceDecision(
                    mention_ids=record.mention_ids,
                    action="keep_unresolved",
                    evidence_quotes=[record.evidence_quotes[-1]],
                    confidence=0.5,
                    rationale="identity evidence remains insufficient",
                )
                for record in records
            ]
        )


@pytest.mark.asyncio
async def test_ten_chunk_boundary_and_tail_batch_are_both_converged(tmp_path: Path) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'entity-resolution.db'}"
    config = Config("alembic.ini")
    config.cmd_opts = type("Options", (), {"x": [f"database_url={database_url}"]})()
    await to_thread(command.upgrade, config, "head")
    engine = create_async_engine(database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    store = LocalArtifactStore(tmp_path / "artifacts")
    text = "\n".join(
        f"第{ordinal}章\n唐三仍是黑发。" for ordinal in range(1, 12)
    )
    resolver = RecordingResolver()

    async with sessions() as session:
        service = IngestionService(session, store)
        novel = await service.upload(filename="eleven.txt", data=text.encode())
        ingestion = await service.create_run(novel.id, "eleven-ingest")
        assert ingestion is not None
        await process_ingestion_run(session, store, ingestion.id, target_tokens=1_000)
        extraction = await service.create_extraction_run(novel.id, "eleven-extract")
        assert extraction is not None
        await process_extraction_run(
            session,
            ElevenChapterVisualProvider(),
            extraction.id,
            entity_provider=resolver,
        )

        assert len(resolver.resolution_inputs) == 11
        assert len(resolver.resolution_inputs[2].cumulative_memory[0].mention_ids) == 2
        boundaries = [
            (item.start_chunk_ordinal, item.end_chunk_ordinal, item.final_batch)
            for item in resolver.convergence_inputs
        ]
        assert boundaries == [
            (0, 9, False),
            (10, 10, True),
        ]
        batches = list(
            await session.scalars(
                select(CharacterConvergenceBatchORM).order_by(
                    CharacterConvergenceBatchORM.batch_index
                )
            )
        )
        assert len(batches) == 2
        assert all(item.status == "completed" for item in batches)
        observations = list(await session.scalars(select(FeatureObservationORM)))
        assert len(observations) == 11
        assert all(item.mention_span_id is not None for item in observations)

        calls_before = (
            len(resolver.resolution_inputs),
            len(resolver.convergence_inputs),
        )
        await process_extraction_run(
            session,
            ElevenChapterVisualProvider(),
            extraction.id,
            entity_provider=resolver,
        )
        assert (
            len(resolver.resolution_inputs),
            len(resolver.convergence_inputs),
        ) == calls_before
        assert len(list(await session.scalars(select(FeatureObservationORM)))) == 11

    await engine.dispose()


@pytest.mark.asyncio
async def test_convergence_shards_and_repairs_only_the_omitted_record(
    tmp_path: Path,
) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'shard-repair.db'}"
    config = Config("alembic.ini")
    config.cmd_opts = type("Options", (), {"x": [f"database_url={database_url}"]})()
    await to_thread(command.upgrade, config, "head")
    engine = create_async_engine(database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    store = LocalArtifactStore(tmp_path / "shard-repair-artifacts")
    resolver = RepairingShardResolver()

    async with sessions() as session:
        service = IngestionService(session, store)
        novel = await service.upload(
            filename="three.txt",
            data="第一章\n甲客、乙客和丙客同时出现。".encode(),
        )
        ingestion = await service.create_run(novel.id, "shard-repair-ingest")
        assert ingestion is not None
        await process_ingestion_run(session, store, ingestion.id, target_tokens=1_000)
        extraction = await service.create_extraction_run(novel.id, "shard-repair-extract")
        assert extraction is not None
        await process_extraction_run(
            session,
            ThreePersonVisualProvider(),
            extraction.id,
            entity_provider=resolver,
            entity_convergence_shard_max_mentions=2,
            entity_convergence_shard_max_input_tokens=100_000,
            entity_convergence_shard_max_output_tokens=100_000,
            entity_convergence_repair_max_attempts=2,
        )

        assert [len(item.provisional_memory) for item in resolver.convergence_inputs] == [
            2,
            1,
            1,
        ]
        assert (
            resolver.convergence_inputs[1].provisional_memory[0].memory_id
            == resolver.convergence_inputs[0].provisional_memory[1].memory_id
        )
        provider_events = list(
            await session.scalars(
                select(RunEventORM)
                .where(
                    RunEventORM.run_id == extraction.id,
                    RunEventORM.event_type == "provider.entity_convergence.completed",
                )
                .order_by(RunEventORM.sequence)
            )
        )
        assert [item.payload["call_kind"] for item in provider_events] == [
            "initial",
            "repair",
            "initial",
        ]
        frontier_event = await session.scalar(
            select(RunEventORM).where(
                RunEventORM.run_id == extraction.id,
                RunEventORM.event_type == "entity.convergence.frontier.completed",
            )
        )
        assert frontier_event is not None
        sharding = frontier_event.payload["convergence_sharding"]
        assert sharding["shard_count"] == 2
        assert sharding["repair_attempts"] == 1
        assert sharding["initial_uncovered_mentions"] == 1
        assert sharding["repaired_mentions"] == 1
        assert sharding["fallback_mentions"] == 0
        batch = await session.scalar(select(CharacterConvergenceBatchORM))
        assert batch is not None
        assert batch.status == "completed"

    await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("case_name", "entity_max_calls", "expected_calls", "expected_repairs", "budget_exhausted"),
    [
        ("repair-limit", 2_000, 3, 2, False),
        ("call-budget", 2, 1, 0, True),
    ],
)
async def test_exhausted_convergence_repairs_are_explicit_warnings_and_recoverable(
    tmp_path: Path,
    case_name: str,
    entity_max_calls: int,
    expected_calls: int,
    expected_repairs: int,
    budget_exhausted: bool,
) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / f'repair-warning-{case_name}.db'}"
    config = Config("alembic.ini")
    config.cmd_opts = type("Options", (), {"x": [f"database_url={database_url}"]})()
    await to_thread(command.upgrade, config, "head")
    engine = create_async_engine(database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    store = LocalArtifactStore(tmp_path / "repair-warning-artifacts")
    resolver = RepairingShardResolver(always_omit=True)

    async with sessions() as session:
        service = IngestionService(session, store)
        novel = await service.upload(
            filename="warning.txt",
            data="第一章\n甲客、乙客和丙客同时出现。".encode(),
        )
        ingestion = await service.create_run(novel.id, f"repair-warning-ingest-{case_name}")
        assert ingestion is not None
        await process_ingestion_run(session, store, ingestion.id, target_tokens=1_000)
        extraction = await service.create_extraction_run(
            novel.id, f"repair-warning-extract-{case_name}"
        )
        assert extraction is not None
        await process_extraction_run(
            session,
            ThreePersonVisualProvider(),
            extraction.id,
            entity_provider=resolver,
            entity_convergence_shard_max_mentions=8,
            entity_convergence_shard_max_input_tokens=100_000,
            entity_convergence_shard_max_output_tokens=100_000,
            entity_convergence_repair_max_attempts=2,
            entity_max_calls=entity_max_calls,
        )

        assert len(resolver.convergence_inputs) == expected_calls
        batch = await session.scalar(select(CharacterConvergenceBatchORM))
        assert batch is not None
        assert batch.status == "completed_with_warnings"
        assert batch.result is not None
        assert sum(len(item["mention_ids"]) for item in batch.result["decisions"]) == 3
        assert all(item["action"] == "keep_unresolved" for item in batch.result["decisions"])
        event = await session.scalar(
            select(RunEventORM).where(
                RunEventORM.run_id == extraction.id,
                RunEventORM.event_type == "entity.convergence.frontier.completed",
            )
        )
        assert event is not None
        trace = event.payload["convergence_sharding"]
        assert trace["repair_attempts"] == expected_repairs
        assert trace["repair_call_budget_exhausted"] is budget_exhausted
        assert trace["fallback_mentions"] == 3
        calls_before = len(resolver.convergence_inputs)
        await process_extraction_run(
            session,
            ThreePersonVisualProvider(),
            extraction.id,
            entity_provider=resolver,
        )
        assert len(resolver.convergence_inputs) == calls_before

    await engine.dispose()


@pytest.mark.asyncio
async def test_convergence_frontier_does_not_repeat_untouched_unresolved(
    tmp_path: Path,
) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'frontier.db'}"
    config = Config("alembic.ini")
    config.cmd_opts = type("Options", (), {"x": [f"database_url={database_url}"]})()
    await to_thread(command.upgrade, config, "head")
    engine = create_async_engine(database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    store = LocalArtifactStore(tmp_path / "frontier-artifacts")
    chapters = ["第一章\n旧人出现。"]
    chapters.extend(f"第{ordinal}章\n此章无人。" for ordinal in range(2, 11))
    chapters.append("第十一章\n新人出现。")
    resolver = FrontierResolver()

    async with sessions() as session:
        service = IngestionService(session, store)
        novel = await service.upload(filename="frontier.txt", data="\n".join(chapters).encode())
        ingestion = await service.create_run(novel.id, "frontier-ingest")
        assert ingestion is not None
        await process_ingestion_run(session, store, ingestion.id, target_tokens=1_000)
        extraction = await service.create_extraction_run(novel.id, "frontier-extract")
        assert extraction is not None
        await process_extraction_run(
            session,
            FrontierVisualProvider(),
            extraction.id,
            entity_provider=resolver,
        )

        assert len(resolver.convergence_inputs) == 2
        first_names = {
            name
            for record in resolver.convergence_inputs[0].provisional_memory
            for name in record.names
        }
        second_names = {
            name
            for record in resolver.convergence_inputs[1].provisional_memory
            for name in record.names
        }
        assert first_names == {"旧人"}
        assert second_names == {"新人"}

        batches = list(
            await session.scalars(
                select(CharacterConvergenceBatchORM).order_by(
                    CharacterConvergenceBatchORM.batch_index
                )
            )
        )
        assert len(batches) == 2
        assert batches[-1].memory_after is not None
        final_unresolved = [
            item for item in batches[-1].memory_after if item["status"] == "unresolved"
        ]
        assert {name for item in final_unresolved for name in item["names"]} == {
            "旧人",
            "新人",
        }

        frontier_events = list(
            await session.scalars(
                select(RunEventORM)
                .where(
                    RunEventORM.run_id == extraction.id,
                    RunEventORM.event_type == "entity.convergence.frontier.completed",
                )
                .order_by(RunEventORM.sequence)
            )
        )
        assert len(frontier_events) == 2
        second_trace = frontier_events[-1].payload["convergence_frontier"]
        assert second_trace["nonstable_records_before"] == 2
        assert second_trace["frontier_records"] == 1
        assert second_trace["deferred_records"] == 1
        assert second_trace["provider_omitted_mentions"] == 0
        assert "evidence_quotes" not in second_trace

    await engine.dispose()


@pytest.mark.asyncio
async def test_explicit_boy_identity_does_not_contaminate_a_later_boy(
    tmp_path: Path,
) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'boy-isolation.db'}"
    config = Config("alembic.ini")
    config.cmd_opts = type("Options", (), {"x": [f"database_url={database_url}"]})()
    await to_thread(command.upgrade, config, "head")
    engine = create_async_engine(database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    store = LocalArtifactStore(tmp_path / "boy-artifacts")
    text = (
        "第一章\n山顶上坐着一个男孩，生着黑发。\n"
        "第二章\n这个男孩正是唐三。\n"
        "第三章\n河边又站着一个男孩，穿着红衣。"
    )

    async with sessions() as session:
        service = IngestionService(session, store)
        novel = await service.upload(filename="boys.txt", data=text.encode())
        ingestion = await service.create_run(novel.id, "boys-ingest")
        assert ingestion is not None
        await process_ingestion_run(session, store, ingestion.id, target_tokens=1_000)
        extraction = await service.create_extraction_run(novel.id, "boys-extract")
        assert extraction is not None
        await process_extraction_run(
            session,
            AmbiguousBoyVisualProvider(),
            extraction.id,
            entity_provider=AmbiguousBoyResolver(),
        )

        characters = list(await session.scalars(select(CharacterORM)))
        assert [item.canonical_name for item in characters] == ["唐三"]
        observations = list(await session.scalars(select(FeatureObservationORM)))
        assert [(item.field_path, item.value) for item in observations] == [
            ("hair.color", "黑色")
        ]
        mentions = list(
            await session.scalars(select(MentionSpanORM).order_by(MentionSpanORM.created_at))
        )
        resolved = [item for item in mentions if item.resolved_character_id is not None]
        assert {item.mention_text for item in resolved} == {"男孩", "唐三"}
        assert all(item.resolved_character_id == characters[0].id for item in resolved)
        unresolved = [item for item in mentions if item.resolved_character_id is None]
        assert len(unresolved) == 1
        assert unresolved[0].mention_text == "男孩"

    await engine.dispose()
