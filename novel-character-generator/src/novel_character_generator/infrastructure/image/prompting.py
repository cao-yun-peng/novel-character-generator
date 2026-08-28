from __future__ import annotations

import re
from collections.abc import Callable
from typing import cast

from novel_character_generator.application.ports.image_generation import (
    ImagePromptRenderer,
    PromptBlock,
    PromptSourceBinding,
    RenderedImagePrompt,
    RenderedPromptClause,
)
from novel_character_generator.domain.entities.image import ImageRenderSpec

CANONICAL_ZH_RENDERER_ID = "canonical-zh"
CANONICAL_ZH_RENDERER_VERSION = "canonical-zh-character-v1"

_BLOCKS: tuple[tuple[PromptBlock, str, str], ...] = (
    ("identity", "角色身份", "identity_prompt_block"),
    ("stage", "当前阶段", "stage_prompt_block"),
    ("outfit", "服装配饰", "outfit_prompt_block"),
    ("performance", "动作与表演", "performance_prompt_block"),
    ("environment", "场景环境", "environment_prompt_block"),
    ("art_direction", "美术与构图", "art_direction_prompt_block"),
)

_VALUE_TRANSLATIONS = {
    "adolescence": "青春期",
    "black": "黑色",
    "childhood": "儿童阶段",
    "full body": "全身",
    "illustration": "插画",
    "oval": "椭圆形",
    "pale": "苍白",
    "school uniform": "校服",
    "short": "短发",
    "small": "瘦小",
    "standing": "自然站立",
    "sturdier": "更健壮",
    "sweaty": "带有汗水",
    "toward viewer": "朝向观者",
}

_PATH_TEMPLATES = {
    "accessory": "配饰为{value}",
    "accessories.wrist": "腕部佩戴{value}",
    "action": "动作是{value}",
    "age": "年龄为{value}",
    "age_stage": "年龄阶段为{value}",
    "art_direction.color_palette": "整体色彩为{value}",
    "art_direction.lighting": "光线为{value}",
    "art_direction.medium": "采用{value}表现",
    "art_direction.style": "视觉风格为{value}",
    "body.build": "体型为{value}",
    "cleanliness": "外观状态为{value}",
    "clothing.color": "服装颜色为{value}",
    "clothing.style": "穿着{value}",
    "composition.camera": "镜头为{value}",
    "composition.framing": "画面构图为{value}",
    "composition.shot": "景别为{value}",
    "composition.view": "观察视角为{value}",
    "composition.view_angle": "观察视角为{value}",
    "environment.background": "背景为{value}",
    "environment.location": "地点为{value}",
    "environment.time": "时间为{value}",
    "eyes.color": "眼睛颜色为{value}",
    "face.eyes": "眼神特征为{value}",
    "face.shape": "脸型为{value}",
    "gaze": "视线{value}",
    "hair.color": "头发颜色为{value}",
    "hair.length": "发型为{value}",
    "held_objects": "手持{value}",
    "pose.body": "身体姿势为{value}",
    "skin.color": "肤色为{value}",
    "style_preset": "采用{value}",
    "visible_expression.expression": "可见表情为{value}",
}

_SEGMENT_LABELS = {
    "background": "背景",
    "build": "体型",
    "camera": "镜头",
    "color": "颜色",
    "color_palette": "色彩",
    "expression": "表情",
    "framing": "构图",
    "length": "长度",
    "lighting": "光线",
    "location": "地点",
    "medium": "媒介",
    "shape": "形状",
    "shot": "景别",
    "style": "样式",
    "time": "时间",
    "view": "视角",
    "view_angle": "视角",
}

_STYLE_PRESETS = {
    "illustration-v1": "小说角色概念插画",
}


class CanonicalChinesePromptRendererV1:
    """Deterministically translates sourced canonical fields into visual Chinese."""

    renderer = CANONICAL_ZH_RENDERER_ID
    version = CANONICAL_ZH_RENDERER_VERSION

    def render(self, spec: ImageRenderSpec) -> RenderedImagePrompt:
        instruction = self._instruction(spec)
        clauses = [
            RenderedPromptClause(
                text=instruction,
                polarity="positive",
                block="instruction",
            )
        ]
        sections = [instruction]
        for block, label, attribute in _BLOCKS:
            raw_values = cast(list[str], getattr(spec, attribute))
            if not raw_values:
                continue
            rendered_values: list[str] = []
            for index, raw in enumerate(raw_values):
                field_path, value = _parse_structured_clause(raw, block, index)
                refs = spec.source_map.get(field_path)
                if not refs:
                    raise ValueError(f"prompt_source_missing:{field_path}")
                rendered = _render_field(field_path, value)
                rendered_values.append(rendered)
                clauses.append(
                    RenderedPromptClause(
                        text=rendered,
                        polarity="positive",
                        block=block,
                        source_bindings=[
                            PromptSourceBinding(field_path=field_path, source_refs=refs)
                        ],
                    )
                )
            sections.append(f"{label}：{'；'.join(rendered_values)}。")

        negative_values: list[str] = []
        for index, raw in enumerate(spec.negative_constraints):
            field_path = f"negative_constraints[{index}]"
            refs = spec.source_map.get(field_path)
            if not refs:
                raise ValueError(f"prompt_source_missing:{field_path}")
            value = raw.strip()
            if not value:
                raise ValueError(f"empty_negative_prompt_clause:{index}")
            negative_values.append(value)
            clauses.append(
                RenderedPromptClause(
                    text=value,
                    polarity="negative",
                    block="negative",
                    source_bindings=[
                        PromptSourceBinding(field_path=field_path, source_refs=refs)
                    ],
                )
            )
        return RenderedImagePrompt(
            renderer=self.renderer,
            version=self.version,
            positive_prompt="\n".join(sections),
            negative_prompt="，".join(negative_values),
            clauses=clauses,
        )

    @staticmethod
    def _instruction(spec: ImageRenderSpec) -> str:
        layout = "角色设定图" if spec.render_layout == "character_sheet" else "单张角色图"
        return f"生成{layout}；只呈现一个主要角色，严格遵循已声明设定，不添加人物事实。"


PromptRendererFactory = Callable[[], ImagePromptRenderer]


class ImagePromptRendererRegistry:
    def __init__(self) -> None:
        self._factories: dict[str, PromptRendererFactory] = {}

    def register(self, name: str, factory: PromptRendererFactory) -> None:
        normalized = name.strip().lower()
        if not normalized:
            raise ValueError("invalid_image_prompt_renderer_name")
        if normalized in self._factories:
            raise ValueError(f"image_prompt_renderer_already_registered:{normalized}")
        self._factories[normalized] = factory

    def create(self, name: str) -> ImagePromptRenderer:
        normalized = name.strip().lower()
        factory = self._factories.get(normalized)
        if factory is None:
            available = ",".join(self.names())
            raise RuntimeError(
                f"image_prompt_renderer_not_registered:{normalized};available={available}"
            )
        renderer = factory()
        if renderer.renderer != normalized:
            raise RuntimeError(
                f"image_prompt_renderer_identity_mismatch:{normalized}:{renderer.renderer}"
            )
        return renderer

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._factories))


image_prompt_renderer_registry = ImagePromptRendererRegistry()
image_prompt_renderer_registry.register(
    CANONICAL_ZH_RENDERER_ID,
    CanonicalChinesePromptRendererV1,
)


def create_image_prompt_renderer(name: str) -> ImagePromptRenderer:
    return image_prompt_renderer_registry.create(name)


def _parse_structured_clause(raw: str, block: PromptBlock, index: int) -> tuple[str, str]:
    field_path, separator, value = raw.partition(": ")
    field_path = field_path.strip()
    value = value.strip()
    if not separator or not field_path or not value:
        raise ValueError(f"unstructured_prompt_clause:{block}:{index}")
    return field_path, value


def _render_field(field_path: str, raw_value: str) -> str:
    value = _translate_value(field_path, raw_value)
    normalized_path = re.sub(r"\[\d+\]", "", field_path)
    template = _PATH_TEMPLATES.get(field_path) or _PATH_TEMPLATES.get(normalized_path)
    if template is not None:
        return template.format(value=value)
    leaf = normalized_path.rsplit(".", 1)[-1]
    label = _SEGMENT_LABELS.get(leaf, leaf.replace("_", " "))
    return f"{label}为{value}"


def _translate_value(field_path: str, raw_value: str) -> str:
    value = raw_value.strip()
    if field_path == "style_preset":
        return _STYLE_PRESETS.get(value, value)
    return _VALUE_TRANSLATIONS.get(value.lower(), value)
