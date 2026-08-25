from typing import Any, Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, Field


class VisualEvidencePassage(BaseModel):
    passage_id: UUID
    chapter_ordinal: int
    ordinal: int
    previous_passage_id: UUID | None
    next_passage_id: UUID | None
    content: str


class VisualEvidencePacket(BaseModel):
    character_id: UUID
    canonical_name: str
    aliases: list[str] = Field(default_factory=list)
    field_groups: list[str]
    life_phase_key: str | None = None
    passages: list[VisualEvidencePassage]


class VisualEvidenceDraft(BaseModel):
    character_id: UUID | None
    retrieval_passage_id: UUID
    field_path: str
    value: Any
    evidence_quote: str
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    evidence_kind: Literal["direct", "contextual", "inferred"]
    epistemic_status: Literal[
        "asserted", "negated", "inferred", "uncertain", "style_default"
    ]
    confidence: float = Field(ge=0, le=1)
    life_phase_key: str | None = Field(default=None, max_length=100)
    life_phase_label: str | None = Field(default=None, max_length=100)


class VisualEnrichmentResult(BaseModel):
    observations: list[VisualEvidenceDraft] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    usage: dict[str, int] = Field(default_factory=dict)
    provider_request_id: str | None = None
    finish_reason: str | None = None


class VisualEnrichmentProvider(Protocol):
    provider: str
    model: str
    model_revision: str | None
    version: str

    async def extract_visual_evidence(
        self, packet: VisualEvidencePacket
    ) -> VisualEnrichmentResult: ...
