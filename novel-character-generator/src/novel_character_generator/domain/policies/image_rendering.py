from __future__ import annotations

import hashlib
import json
from typing import Any, cast
from uuid import UUID

from pydantic import ValidationError

from novel_character_generator.domain.entities.image import (
    CharacterDesignGap,
    FieldSourceRef,
    GenerationMode,
    ImageRenderSpec,
    ReferenceAssetBinding,
    RenderBlock,
    RenderReadinessReport,
    ResolvedCharacterRenderFields,
    SceneRenderBrief,
    SourcedRenderField,
)

SCENE_BRIEF_SCHEMA_VERSION = "scene-render-brief-v1"
IMAGE_RENDER_SPEC_SCHEMA_VERSION = "image-render-spec-v1"
IMAGE_RENDER_COMPILER_VERSION = "image-render-compiler-v1"
RENDER_READINESS_POLICY_VERSION = "render-readiness-v1"
RESOLVED_RENDER_FIELDS_SCHEMA_VERSION = "resolved-character-render-fields-v1"

_IDENTITY_ROOTS = frozenset(
    {
        "body",
        "distinctive_marks",
        "eyes",
        "face",
        "facial_hair",
        "hair",
        "skin",
    }
)
_STAGE_ROOTS = frozenset(
    {
        "age",
        "age_stage",
        "cleanliness",
        "disguise",
        "injuries",
        "injury",
        "subject",
    }
)
_OUTFIT_ROOTS = frozenset({"accessory", "accessories", "clothing"})
_SUPPORTED_SCENE_FIELDS = frozenset(
    {
        "action",
        "art_direction",
        "composition",
        "environment",
        "gaze",
        "held_objects",
        "negative_constraints",
        "output_parameters",
        "pose",
        "reference_assets",
        "visible_expression",
    }
)
_CONSISTENT_SCENE_FIELDS = ("environment", "art_direction", "composition")
_SUPPORTED_OUTPUT_PARAMETERS = frozenset({"aspect_ratio", "height", "width"})
_FIELD_BLOCKS = frozenset({"identity", "stage", "outfit"})


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def _canonical_hash(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode()).hexdigest()


def _flatten(value: dict[str, Any], prefix: str = "") -> list[tuple[str, Any]]:
    result: list[tuple[str, Any]] = []
    for key in sorted(value):
        item = value[key]
        path = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(item, dict):
            result.extend(_flatten(item, path))
        elif item is not None and item != "" and item != []:
            result.append((path, item))
    return result


def _prompt_value(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    return _canonical_json(value)


def _prompt_line(path: str, value: Any) -> str:
    return f"{path}: {_prompt_value(value)}"


def _mapping(value: object, field_name: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"invalid_scene_field:{field_name}")
    return {str(key): item for key, item in value.items()}


def _list(value: object, field_name: str) -> list[Any]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"invalid_scene_field:{field_name}")
    return list(value)


def _source_refs(snapshot: dict[str, object], path: str) -> list[FieldSourceRef]:
    raw_provenance = snapshot.get("field_provenance")
    if isinstance(raw_provenance, dict) and path in raw_provenance:
        raw_items = raw_provenance[path]
        if not isinstance(raw_items, list):
            raise ValueError(f"invalid_field_provenance:{path}")
        try:
            structured_refs = [FieldSourceRef.model_validate(item) for item in raw_items]
        except ValidationError as error:
            raise ValueError(f"invalid_field_provenance:{path}") from error
        if not structured_refs:
            raise ValueError(f"empty_field_provenance:{path}")
        return structured_refs
    raw_map = snapshot.get("field_sources")
    raw_sources_value = raw_map.get(path, []) if isinstance(raw_map, dict) else []
    raw_sources = raw_sources_value if isinstance(raw_sources_value, list) else []
    refs: list[FieldSourceRef] = []
    for raw_source in raw_sources:
        try:
            source_id = UUID(str(raw_source))
        except ValueError:
            continue
        refs.append(
            FieldSourceRef(
                source_kind="novel_asserted",
                source_id=source_id,
                evidence_ids=[source_id],
            )
        )
    if not refs:
        refs.append(FieldSourceRef(source_kind="legacy_approved_profile"))
    return refs


def build_scene_render_brief(
    snapshot: dict[str, object],
    render_overrides: dict[str, object],
    *,
    approval_status: str = "draft",
) -> SceneRenderBrief:
    unknown = sorted(set(render_overrides) - _SUPPORTED_SCENE_FIELDS)
    if unknown:
        raise ValueError(f"unsupported_render_override_fields:{','.join(unknown)}")
    raw_references = _list(
        render_overrides.get("reference_assets", []), "reference_assets"
    )
    try:
        references = [
            ReferenceAssetBinding.model_validate(item)
            for item in raw_references
        ]
    except ValidationError as error:
        raise ValueError("invalid_reference_asset_binding") from error
    source_map: dict[str, list[FieldSourceRef]] = {}
    for key, value in render_overrides.items():
        if key == "reference_assets" or value in (None, "", [], {}):
            continue
        if key in {"pose", "visible_expression", "environment", "art_direction", "composition"}:
            for path, _ in _flatten(_mapping(value, key)):
                source_map[f"{key}.{path}"] = [
                    FieldSourceRef(source_kind="human_decision")
                ]
        elif key == "held_objects":
            for index, _ in enumerate(_list(value, key)):
                source_map[f"held_objects[{index}]"] = [
                    FieldSourceRef(source_kind="human_decision")
                ]
        elif key == "negative_constraints":
            continue
        elif key == "output_parameters":
            for path, _ in _flatten(_mapping(value, key)):
                source_map[f"output_parameters.{path}"] = [
                    FieldSourceRef(source_kind="human_decision")
                ]
        else:
            source_map[key] = [FieldSourceRef(source_kind="human_decision")]
    for item in references:
        source_map[f"reference_assets.{item.role}:{item.artifact_id}"] = [
            FieldSourceRef(source_kind="reference_asset")
        ]
    raw_target = snapshot.get("target")
    target = raw_target if isinstance(raw_target, dict) else {}
    raw_expression = render_overrides.get("visible_expression")
    expression = (
        None
        if raw_expression is None
        else _mapping(raw_expression, "visible_expression")
    )
    output_parameters = _mapping(
        render_overrides.get("output_parameters", {}), "output_parameters"
    )
    unsupported_parameters = sorted(
        set(output_parameters) - _SUPPORTED_OUTPUT_PARAMETERS
    )
    if unsupported_parameters:
        raise ValueError(
            "unsupported_output_parameters:" + ",".join(unsupported_parameters)
        )
    negative_constraints = sorted(
        {
            str(item).strip()
            for item in _list(
                render_overrides.get("negative_constraints", []),
                "negative_constraints",
            )
            if str(item).strip()
        }
    )
    references.sort(key=lambda item: (item.role, str(item.artifact_id), item.weight or 0))
    for index, _ in enumerate(negative_constraints):
        source_map[f"negative_constraints[{index}]"] = [
            FieldSourceRef(source_kind="human_decision")
        ]
    payload: dict[str, object] = {
        "schema_version": SCENE_BRIEF_SCHEMA_VERSION,
        "character_snapshot_hash": str(snapshot["snapshot_hash"]),
        "target_scene_id": target.get("scene_id"),
        "pose": _mapping(render_overrides.get("pose", {}), "pose"),
        "action": render_overrides.get("action"),
        "gaze": render_overrides.get("gaze"),
        "visible_expression": expression,
        "held_objects": _list(render_overrides.get("held_objects", []), "held_objects"),
        "environment": _mapping(
            render_overrides.get("environment", {}), "environment"
        ),
        "art_direction": _mapping(
            render_overrides.get("art_direction", {}), "art_direction"
        ),
        "composition": _mapping(
            render_overrides.get("composition", {}), "composition"
        ),
        "negative_constraints": negative_constraints,
        "reference_assets": [item.model_dump(mode="json") for item in references],
        "output_parameters": output_parameters,
        "source_map": {
            key: [item.model_dump(mode="json") for item in value]
            for key, value in source_map.items()
        },
        "approval_status": approval_status,
    }
    payload["brief_hash"] = _canonical_hash(payload)
    try:
        return SceneRenderBrief.model_validate(payload)
    except ValidationError as error:
        raise ValueError("invalid_scene_render_brief") from error


def adapt_resolved_character_fields(
    snapshot: dict[str, object],
) -> ResolvedCharacterRenderFields:
    appearance = snapshot.get("appearance")
    if not isinstance(appearance, dict):
        raise ValueError("resolved_snapshot_appearance_missing")
    fields: list[SourcedRenderField] = []
    unsupported: set[str] = set()
    raw_blocks = snapshot.get("field_blocks")
    field_blocks = raw_blocks if isinstance(raw_blocks, dict) else {}
    for path, value in _flatten(appearance):
        root = path.split(".", 1)[0]
        raw_block = field_blocks.get(path, field_blocks.get(root))
        if raw_block is not None and raw_block not in _FIELD_BLOCKS:
            raise ValueError(f"invalid_field_block:{path}")
        block = str(raw_block) if raw_block is not None else None
        resolved_block: str | None = None
        if block == "identity" or block is None and root in _IDENTITY_ROOTS:
            resolved_block = "identity"
        elif block == "stage" or block is None and root in _STAGE_ROOTS:
            resolved_block = "stage"
        elif block == "outfit" or block is None and root in _OUTFIT_ROOTS:
            resolved_block = "outfit"
        else:
            unsupported.add(root)
        if resolved_block is not None:
            fields.append(
                SourcedRenderField(
                    field_path=path,
                    value=value,
                    block=cast(RenderBlock, resolved_block),
                    source_refs=_source_refs(snapshot, path),
                )
            )
    raw_palette = snapshot.get("palette")
    if isinstance(raw_palette, dict):
        for path, value in _flatten(raw_palette, "palette"):
            fields.append(
                SourcedRenderField(
                    field_path=path,
                    value=value,
                    block="identity",
                    source_refs=_source_refs(snapshot, path),
                )
            )
    if unsupported:
        raise ValueError(f"unsupported_snapshot_visual_roots:{','.join(sorted(unsupported))}")
    return ResolvedCharacterRenderFields(
        schema_version=RESOLVED_RENDER_FIELDS_SCHEMA_VERSION,
        snapshot_hash=str(snapshot.get("snapshot_hash")),
        fields=fields,
    )


def evaluate_render_readiness(
    *,
    identity: list[SourcedRenderField],
    stage: list[SourcedRenderField],
    outfit: list[SourcedRenderField],
    brief: SceneRenderBrief,
    provenance_complete: bool,
    profile_approved: bool,
    workflow_frozen: bool,
) -> RenderReadinessReport:
    gaps: list[CharacterDesignGap] = []
    if not identity:
        gaps.append(
            CharacterDesignGap(
                field_path="identity",
                state="not_stated",
                importance="blocking",
            )
        )
    if not outfit:
        gaps.append(
            CharacterDesignGap(
                field_path="outfit",
                state="not_stated",
                importance="blocking",
            )
        )
    if not stage:
        gaps.append(
            CharacterDesignGap(
                field_path="stage",
                state="unknown",
                importance="blocking",
            )
        )
    if not provenance_complete:
        gaps.append(
            CharacterDesignGap(
                field_path="field_provenance",
                state="unknown",
                importance="blocking",
            )
        )
    concept_ready = bool(identity or stage or outfit)
    character_design_ready = (
        concept_ready
        and profile_approved
        and provenance_complete
        and bool(identity)
        and bool(stage)
        and bool(outfit)
    )
    missing_scene_fields = [
        field
        for field in _CONSISTENT_SCENE_FIELDS
        if not getattr(brief, field)
    ]
    missing_reference_roles = (
        []
        if any(item.role == "identity" for item in brief.reference_assets)
        else ["identity"]
    )
    consistent_scene_ready = (
        character_design_ready
        and brief.approval_status == "approved"
        and not missing_scene_fields
        and bool(brief.negative_constraints)
        and not missing_reference_roles
        and workflow_frozen
    )
    return RenderReadinessReport(
        concept_ready=concept_ready,
        character_design_ready=character_design_ready,
        consistent_scene_ready=consistent_scene_ready,
        blocking_design_gaps=gaps,
        missing_scene_fields=missing_scene_fields,
        missing_reference_roles=missing_reference_roles,
        policy_version=RENDER_READINESS_POLICY_VERSION,
    )


def enforce_generation_mode(
    mode: GenerationMode,
    readiness: RenderReadinessReport,
) -> None:
    allowed = {
        "concept": readiness.concept_ready,
        "character_design": readiness.character_design_ready,
        "consistent_scene": readiness.consistent_scene_ready,
    }
    if not allowed[mode]:
        raise ValueError(f"render_mode_not_ready:{mode}")


def compile_image_render_spec(
    resolved_fields: ResolvedCharacterRenderFields,
    brief: SceneRenderBrief,
    *,
    generation_mode: GenerationMode,
    generate_character_sheet: bool = False,
    style_preset: str | None = None,
    profile_approved: bool = True,
    workflow_frozen: bool = True,
) -> tuple[RenderReadinessReport, ImageRenderSpec]:
    if resolved_fields.snapshot_hash != brief.character_snapshot_hash:
        raise ValueError("scene_brief_snapshot_mismatch")
    identity = [item for item in resolved_fields.fields if item.block == "identity"]
    stage = [item for item in resolved_fields.fields if item.block == "stage"]
    outfit = [item for item in resolved_fields.fields if item.block == "outfit"]
    character_sources = {item.field_path: item.source_refs for item in resolved_fields.fields}
    provenance_complete = all(
        all(ref.source_kind != "legacy_approved_profile" for ref in refs)
        for refs in character_sources.values()
    )
    readiness = evaluate_render_readiness(
        identity=identity,
        stage=stage,
        outfit=outfit,
        brief=brief,
        provenance_complete=provenance_complete,
        profile_approved=profile_approved,
        workflow_frozen=workflow_frozen,
    )
    enforce_generation_mode(generation_mode, readiness)
    source_map: dict[str, list[FieldSourceRef]] = {}
    source_map.update(character_sources)
    source_map.update(brief.source_map)
    if style_preset:
        source_map["style_preset"] = [
            FieldSourceRef(source_kind="legacy_approved_profile")
        ]
    performance = [
        ("pose." + path, value) for path, value in _flatten(brief.pose)
    ]
    if brief.action:
        performance.append(("action", brief.action))
    if brief.gaze:
        performance.append(("gaze", brief.gaze))
    if brief.visible_expression:
        performance.extend(
            ("visible_expression." + path, value)
            for path, value in _flatten(brief.visible_expression)
        )
    performance.extend(
        (f"held_objects[{index}]", item)
        for index, item in enumerate(brief.held_objects)
    )
    environment = _flatten(brief.environment)
    art_direction = [
        *(('art_direction.' + path, value) for path, value in _flatten(brief.art_direction)),
        *(('composition.' + path, value) for path, value in _flatten(brief.composition)),
    ]
    payload: dict[str, object] = {
        "schema_version": IMAGE_RENDER_SPEC_SCHEMA_VERSION,
        "generation_mode": generation_mode,
        "render_layout": "character_sheet" if generate_character_sheet else "single_image",
        "identity_prompt_block": [
            _prompt_line(item.field_path, item.value) for item in identity
        ],
        "stage_prompt_block": [
            _prompt_line(item.field_path, item.value) for item in stage
        ],
        "outfit_prompt_block": [
            _prompt_line(item.field_path, item.value) for item in outfit
        ],
        "performance_prompt_block": [
            _prompt_line(path, value) for path, value in performance
        ],
        "environment_prompt_block": [
            _prompt_line(path, value) for path, value in environment
        ],
        "art_direction_prompt_block": [
            *([_prompt_line("style_preset", style_preset)] if style_preset else []),
            *[_prompt_line(path, value) for path, value in art_direction],
        ],
        "negative_constraints": sorted(set(brief.negative_constraints)),
        "reference_assets": [
            item.model_dump(mode="json") for item in brief.reference_assets
        ],
        "output_parameters": brief.output_parameters,
        "source_map": {
            key: [item.model_dump(mode="json") for item in value]
            for key, value in sorted(source_map.items())
        },
        "compiler_version": IMAGE_RENDER_COMPILER_VERSION,
    }
    payload["spec_hash"] = _canonical_hash(payload)
    return readiness, ImageRenderSpec.model_validate(payload)
