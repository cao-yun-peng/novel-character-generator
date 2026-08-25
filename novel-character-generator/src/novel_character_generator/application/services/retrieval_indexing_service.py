import hashlib
import json
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from novel_character_generator.domain.policies.retrieval import (
    LEXICAL_PROFILE_VERSION,
    RETRIEVAL_PASSAGE_ALGORITHM_VERSION,
)
from novel_character_generator.infrastructure.db.orm import (
    PipelineRunORM,
    RetrievalIndexBuildORM,
)
from novel_character_generator.infrastructure.db.repositories.retrieval import RetrievalRepository
from novel_character_generator.settings import Settings


class RetrievalIndexingService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.repository = RetrievalRepository(session)

    def _config_hash(self) -> str:
        config = {
            "index_version": self.settings.retrieval_index_version,
            "passage_algorithm_version": RETRIEVAL_PASSAGE_ALGORITHM_VERSION,
            "target_tokens": self.settings.retrieval_passage_target_tokens,
            "overlap_tokens": self.settings.retrieval_passage_overlap_tokens,
            "lexical_provider": self.settings.retrieval_lexical_provider,
            "lexical_profile_version": self.settings.retrieval_lexical_profile_version,
            "embedding_provider": self.settings.embedding_provider,
            "embedding_model": self.settings.embedding_model,
            "embedding_model_revision": self.settings.embedding_model_revision,
            "embedding_dimension": self.settings.embedding_dimension,
            "embedding_profile_version": self.settings.embedding_profile_version,
            "embedding_normalization": self.settings.embedding_normalization,
            "embedding_document_prefix": self.settings.embedding_document_prefix,
            "embedding_query_prefix": self.settings.embedding_query_prefix,
        }
        encoded = json.dumps(config, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode()).hexdigest()

    async def ensure_run(
        self, *, novel_id: UUID, source_document_version_id: UUID
    ) -> tuple[RetrievalIndexBuildORM, PipelineRunORM]:
        if self.settings.retrieval_lexical_profile_version != LEXICAL_PROFILE_VERSION:
            raise ValueError("unsupported_retrieval_lexical_profile_version")
        return await self.repository.ensure_indexing_run(
            novel_id=novel_id,
            source_document_version_id=source_document_version_id,
            index_version=self.settings.retrieval_index_version,
            config_hash=self._config_hash(),
            passage_algorithm_version=RETRIEVAL_PASSAGE_ALGORITHM_VERSION,
            lexical_profile_version=self.settings.retrieval_lexical_profile_version,
            embedding_profile_version=self.settings.embedding_profile_version,
        )
