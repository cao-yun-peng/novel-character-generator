from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

GenerationMode = Literal["concept", "character_design", "consistent_scene"]
RenderBlock = Literal["identity", "stage", "outfit"]
FieldSourceKind = Literal[
    "novel_asserted",
    "human_decision",
    "approved_suggestion",
    "workflow_default",
    "reference_asset",
    "legacy_approved_profile",
]


class _StrictImageModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FieldSourceRef(_StrictImageModel):
    source_kind: FieldSourceKind
    source_id: UUID | None = None
    evidence_ids: list[UUID] = Field(default_factory=list)


class SourcedRenderField(_StrictImageModel):
    field_path: str = Field(min_length=1)
    value: Any
    block: RenderBlock
    source_refs: list[FieldSourceRef] = Field(min_length=1)


class ResolvedCharacterRenderFields(_StrictImageModel):
    schema_version: str
    snapshot_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    fields: list[SourcedRenderField] = Field(default_factory=list)


class CharacterDesignGap(_StrictImageModel):
    field_path: str
    state: Literal["unknown", "not_stated", "conflicted"]
    importance: Literal["blocking", "recommended", "optional"]
    target_stage_key: str | None = None
    candidate_suggestion_ids: list[UUID] = Field(default_factory=list)
    resolution_source: Literal["human_decision", "approved_suggestion"] | None = None


class RenderReadinessReport(_StrictImageModel):
    concept_ready: bool
    character_design_ready: bool
    consistent_scene_ready: bool
    blocking_conflict_ids: list[UUID] = Field(default_factory=list)
    blocking_design_gaps: list[CharacterDesignGap] = Field(default_factory=list)
    missing_scene_fields: list[str] = Field(default_factory=list)
    missing_reference_roles: list[str] = Field(default_factory=list)
    policy_version: str


class ReferenceAssetBinding(_StrictImageModel):
    artifact_id: UUID
    role: Literal["identity", "pose", "structure", "style"]
    weight: float | None = Field(default=None, ge=0, le=2)


class SceneRenderBrief(_StrictImageModel):
    schema_version: str
    character_snapshot_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    target_scene_id: UUID | None = None
    pose: dict[str, Any] = Field(default_factory=dict)
    action: str | None = None
    gaze: str | None = None
    visible_expression: dict[str, Any] | None = None
    held_objects: list[str] = Field(default_factory=list)
    environment: dict[str, Any] = Field(default_factory=dict)
    art_direction: dict[str, Any] = Field(default_factory=dict)
    composition: dict[str, Any] = Field(default_factory=dict)
    negative_constraints: list[str] = Field(default_factory=list)
    reference_assets: list[ReferenceAssetBinding] = Field(default_factory=list)
    output_parameters: dict[str, Any] = Field(default_factory=dict)
    source_map: dict[str, list[FieldSourceRef]] = Field(default_factory=dict)
    approval_status: Literal["draft", "approved"] = "draft"
    brief_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class ImageRenderSpec(_StrictImageModel):
    schema_version: str
    generation_mode: GenerationMode
    render_layout: Literal["single_image", "character_sheet"] = "single_image"
    identity_prompt_block: list[str] = Field(default_factory=list)
    stage_prompt_block: list[str] = Field(default_factory=list)
    outfit_prompt_block: list[str] = Field(default_factory=list)
    performance_prompt_block: list[str] = Field(default_factory=list)
    environment_prompt_block: list[str] = Field(default_factory=list)
    art_direction_prompt_block: list[str] = Field(default_factory=list)
    negative_constraints: list[str] = Field(default_factory=list)
    reference_assets: list[ReferenceAssetBinding] = Field(default_factory=list)
    output_parameters: dict[str, Any] = Field(default_factory=dict)
    source_map: dict[str, list[FieldSourceRef]] = Field(default_factory=dict)
    compiler_version: str
    spec_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


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
