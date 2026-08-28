from uuid import UUID

import pytest

from novel_character_generator.domain.policies.image_rendering import (
    adapt_resolved_character_fields,
    build_scene_render_brief,
    compile_image_render_spec,
)

SNAPSHOT_HASH = "a" * 64
EVIDENCE_ID = UUID("00000000-0000-0000-0000-000000000001")


def _snapshot() -> dict[str, object]:
    return {
        "snapshot_hash": SNAPSHOT_HASH,
        "target": {"scene_id": None},
        "appearance": {
            "face": {"shape": "oval"},
            "hair": {"color": "black", "length": "short"},
            "age_stage": "adolescence",
            "clothing": {"style": "school uniform", "color": "blue"},
        },
        "field_sources": {
            "face.shape": [str(EVIDENCE_ID)],
            "hair.color": [str(EVIDENCE_ID)],
            "hair.length": [str(EVIDENCE_ID)],
            "age_stage": [str(EVIDENCE_ID)],
            "clothing.style": [str(EVIDENCE_ID)],
            "clothing.color": [str(EVIDENCE_ID)],
        },
    }


def test_expected_fields_compile_into_stable_provider_neutral_blocks() -> None:
    overrides = {
        "pose": {"body": "standing"},
        "gaze": "toward viewer",
        "environment": {"location": "studio"},
        "art_direction": {"medium": "illustration"},
        "composition": {"shot": "full body"},
        "negative_constraints": ["extra people", "extra people", "wrong age"],
        "output_parameters": {"width": 768, "height": 1024},
        "reference_assets": [
            {
                "artifact_id": "00000000-0000-0000-0000-000000000002",
                "role": "identity",
                "weight": 1.0,
            }
        ],
    }
    brief = build_scene_render_brief(
        _snapshot(), overrides, approval_status="approved"
    )
    resolved = adapt_resolved_character_fields(_snapshot())
    readiness, first = compile_image_render_spec(
        resolved, brief, generation_mode="consistent_scene"
    )
    _, second = compile_image_render_spec(
        resolved, brief, generation_mode="consistent_scene"
    )

    assert readiness.concept_ready is True
    assert readiness.character_design_ready is True
    assert readiness.consistent_scene_ready is True
    assert first.spec_hash == second.spec_hash
    assert first.identity_prompt_block == [
        "face.shape: oval",
        "hair.color: black",
        "hair.length: short",
    ]
    assert first.stage_prompt_block == ["age_stage: adolescence"]
    assert first.outfit_prompt_block == [
        "clothing.color: blue",
        "clothing.style: school uniform",
    ]
    assert first.performance_prompt_block == [
        "pose.body: standing",
        "gaze: toward viewer",
    ]
    assert first.negative_constraints == ["extra people", "wrong age"]
    assert first.source_map["face.shape"][0].evidence_ids == [EVIDENCE_ID]
    serialized = first.model_dump_json()
    assert "noble" not in serialized
    assert "jewelry" not in serialized


def test_unknown_or_character_level_overrides_fail_closed() -> None:
    with pytest.raises(
        ValueError,
        match="unsupported_render_override_fields:character",
    ):
        build_scene_render_brief(
            _snapshot(),
            {"character": {"hair": {"color": "purple"}}},
        )
    with pytest.raises(
        ValueError,
        match="unsupported_render_override_fields:approval_status",
    ):
        build_scene_render_brief(_snapshot(), {"approval_status": "approved"})


def test_generation_modes_enforce_readiness_without_blocking_concept_mock() -> None:
    snapshot = _snapshot()
    snapshot["appearance"] = {"hair": {"color": "black"}}
    brief = build_scene_render_brief(snapshot, {})
    resolved = adapt_resolved_character_fields(snapshot)

    readiness, spec = compile_image_render_spec(
        resolved,
        brief,
        generation_mode="concept",
    )

    assert spec.generation_mode == "concept"
    assert readiness.concept_ready is True
    assert readiness.character_design_ready is False
    assert {gap.field_path for gap in readiness.blocking_design_gaps} == {
        "outfit",
        "stage",
    }
    with pytest.raises(ValueError, match="render_mode_not_ready:character_design"):
        compile_image_render_spec(
            resolved,
            brief,
            generation_mode="character_design",
        )


def test_consistent_scene_requires_approved_complete_scene_brief() -> None:
    brief = build_scene_render_brief(_snapshot(), {"environment": {"time": "dawn"}})
    resolved = adapt_resolved_character_fields(_snapshot())

    with pytest.raises(ValueError, match="render_mode_not_ready:consistent_scene"):
        compile_image_render_spec(
            resolved,
            brief,
            generation_mode="consistent_scene",
        )


def test_target_catalog_and_explicit_stage_block_are_supported() -> None:
    snapshot = _snapshot()
    snapshot["appearance"] = {
        "subject": {"presentation": "boy"},
        "eyes": {"color": "brown"},
        "facial_hair": {"beard": "none"},
        "hair": {"color": "white"},
        "clothing": {"style": "plain"},
    }
    snapshot["field_blocks"] = {"hair.color": "stage"}
    snapshot["field_provenance"] = {
        path: [
            {
                "source_kind": "human_decision",
                "source_id": None,
                "evidence_ids": [],
            }
        ]
        for path in (
            "subject.presentation",
            "eyes.color",
            "facial_hair.beard",
            "hair.color",
            "clothing.style",
        )
    }

    resolved = adapt_resolved_character_fields(snapshot)

    assert {(item.field_path, item.block) for item in resolved.fields} == {
        ("subject.presentation", "stage"),
        ("eyes.color", "identity"),
        ("facial_hair.beard", "identity"),
        ("hair.color", "stage"),
        ("clothing.style", "outfit"),
    }
