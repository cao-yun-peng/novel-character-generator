from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class TemporalScope(BaseModel):
    model_config = ConfigDict(frozen=True)

    timeline_id: UUID
    start_event_id: UUID | None = None
    end_event_id: UUID | None = None
    start_scene_order: Decimal | None = None
    end_scene_order: Decimal | None = None
    start_chapter_ordinal: int | None = None
    end_chapter_ordinal: int | None = None
    scope_type: Literal["instant", "scene", "chapter", "interval", "persistent", "unknown"]
    presentation_mode: Literal[
        "direct", "flashback", "flashforward", "dream", "illusion", "rumor", "hypothetical"
    ] = "direct"
    reality_status: Literal["canonical", "subjective", "alleged", "counterfactual"] = "canonical"
