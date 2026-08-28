import json
from pathlib import Path

import pytest

from novel_character_generator.domain.entities.image import ImageRenderSpec
from novel_character_generator.infrastructure.image.prompting import (
    CanonicalChinesePromptRendererV1,
    ImagePromptRendererRegistry,
)

GOLDEN_PATH = (
    Path(__file__).parents[1] / "golden" / "dashscope_character_prompt_v1.json"
)


def _source_map(paths: list[str]) -> dict[str, list[dict[str, str]]]:
    return {path: [{"source_kind": "human_decision"}] for path in paths}


def _spec() -> ImageRenderSpec:
    paths = [
        "hair.color",
        "hair.length",
        "skin.color",
        "age",
        "age_stage",
        "body.build",
        "clothing.style",
        "pose.body",
        "gaze",
        "environment.location",
        "environment.time",
        "environment.background",
        "art_direction.medium",
        "art_direction.lighting",
        "composition.shot",
        *[f"negative_constraints[{index}]" for index in range(6)],
    ]
    return ImageRenderSpec(
        schema_version="image-render-spec-v1",
        generation_mode="character_design",
        identity_prompt_block=[
            "hair.color: black",
            "hair.length: short",
            "skin.color: 健康的小麦色",
        ],
        stage_prompt_block=[
            "age: 五、六岁",
            "age_stage: childhood",
            "body.build: 瘦小",
        ],
        outfit_prompt_block=["clothing.style: 朴素的灰色旧布衣"],
        performance_prompt_block=[
            "pose.body: 安静坐在山石上",
            "gaze: 望向东方晨光",
        ],
        environment_prompt_block=[
            "environment.location: 山顶",
            "environment.time: 黎明",
            "environment.background: 远处群山与薄雾",
        ],
        art_direction_prompt_block=[
            "art_direction.medium: 东方玄幻小说角色概念插画",
            "art_direction.lighting: 柔和晨光",
            "composition.shot: full body",
        ],
        negative_constraints=[
            "文字",
            "水印",
            "现代服装",
            "成年人体型",
            "多余手指",
            "模糊面部",
        ],
        output_parameters={"size": "1328*1328"},
        source_map=_source_map(paths),
        compiler_version="image-render-compiler-v1",
        spec_hash="a" * 64,
    )


def test_canonical_renderer_matches_golden_prompt_and_provenance() -> None:
    golden = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))

    rendered = CanonicalChinesePromptRendererV1().render(_spec())
    source_paths = [
        binding.field_path
        for clause in rendered.clauses
        for binding in clause.source_bindings
    ]

    assert rendered.renderer == golden["renderer"]
    assert rendered.version == golden["version"]
    assert rendered.positive_prompt == golden["positive_prompt"]
    assert rendered.negative_prompt == golden["negative_prompt"]
    assert source_paths == golden["source_paths"]
    assert "hair.color" not in rendered.positive_prompt
    assert all(
        binding.source_refs[0].source_kind == "human_decision"
        for clause in rendered.clauses
        for binding in clause.source_bindings
    )


def test_renderer_fails_closed_for_unstructured_or_unprovenanced_clauses() -> None:
    renderer = CanonicalChinesePromptRendererV1()

    with pytest.raises(ValueError, match="unstructured_prompt_clause"):
        renderer.render(
            _spec().model_copy(update={"identity_prompt_block": ["黑色短发"]})
        )
    with pytest.raises(ValueError, match="prompt_source_missing:hair.color"):
        renderer.render(_spec().model_copy(update={"source_map": {}}))


class ExperimentalRenderer(CanonicalChinesePromptRendererV1):
    renderer = "experimental"
    version = "experimental-v1"


class WrongIdentityRenderer(CanonicalChinesePromptRendererV1):
    renderer = "wrong"


def test_prompt_renderer_registry_is_pluggable_and_fails_closed() -> None:
    registry = ImagePromptRendererRegistry()
    registry.register("experimental", ExperimentalRenderer)

    renderer = registry.create("EXPERIMENTAL")

    assert renderer.version == "experimental-v1"
    assert registry.names() == ("experimental",)
    with pytest.raises(RuntimeError, match="not_registered"):
        registry.create("missing")
    with pytest.raises(ValueError, match="already_registered"):
        registry.register("experimental", ExperimentalRenderer)
    mismatch = ImagePromptRendererRegistry()
    mismatch.register("expected", WrongIdentityRenderer)
    with pytest.raises(RuntimeError, match="identity_mismatch"):
        mismatch.create("expected")
