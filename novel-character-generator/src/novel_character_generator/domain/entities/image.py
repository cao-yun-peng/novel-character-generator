from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class CharacterImageSet(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    character_id: UUID
    render_profile_version: int = Field(ge=1)
    version: int = Field(ge=1)
    default_representative_image_id: UUID | None = None
    stage_image_ids: list[UUID] = Field(default_factory=list)
    selection_policy_version: str
    status: Literal["draft", "partially_approved", "approved"] = "draft"


class CharacterStageImage(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    image_set_id: UUID
    appearance_state_id: UUID
    resolved_snapshot_hash: str
    stage_label: str
    representative_event_id: UUID | None = None
    candidate_image_ids: list[UUID] = Field(default_factory=list)
    baseline_image_id: UUID | None = None
    display_order: int = Field(ge=0)
    selection_reason_codes: list[str] = Field(default_factory=list)
