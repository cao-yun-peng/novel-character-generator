from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

EXTRACTION_SCHEMA_VERSION = "visual-observation-v2"

VISUAL_FIELD_ROOTS = frozenset(
    {
        "accessory",
        "accessories",
        "age",
        "age_stage",
        "body",
        "cleanliness",
        "clothing",
        "disguise",
        "distinctive_marks",
        "face",
        "hair",
        "injuries",
        "injury",
        "skin",
    }
)

VISUAL_CATEGORY_LABELS = {
    "accessory": "配饰",
    "accessories": "配饰",
    "age": "年龄",
    "age_stage": "年龄",
    "body": "身体",
    "cleanliness": "整洁状态",
    "clothing": "服装",
    "disguise": "伪装",
    "distinctive_marks": "显著标记",
    "face": "面部",
    "hair": "头发",
    "injuries": "伤势",
    "injury": "伤势",
    "skin": "肤色",
}

FIELD_PATH_ALIASES = {
    "appearance.build": "body.build",
    "appearance.body_build": "body.build",
    "appearance.skin": "skin.color",
    "appearance.skin_color": "skin.color",
    "appearance.hair_color": "hair.color",
    "appearance.hair_length": "hair.length",
    "appearance.clothing": "clothing.style",
    "appearance.clothing_style": "clothing.style",
    "appearance.cleanliness": "cleanliness",
    "build": "body.build",
    "body.type": "body.build",
    "hair.colour": "hair.color",
    "skin.colour": "skin.color",
    "martial_soul": "abilities.martial_spirit",
    "martial_spirit": "abilities.martial_spirit",
    "spirit.name": "abilities.martial_spirit",
    "innate_soul_power": "abilities.innate_soul_power",
    "soul.innate_full_soul_power": "abilities.innate_soul_power",
    "soul_power.innate": "abilities.innate_soul_power",
    "soul_power.innate_full": "abilities.innate_soul_power",
    "soul.twin_martial_spirits": "abilities.twin_martial_spirits",
}

LIFE_PHASE_ALIASES = {
    "previous_life": "past_life",
    "previous-life": "past_life",
    "前世": "past_life",
    "前世唐门": "past_life",
    "唐门前世": "past_life",
    "前一世": "past_life",
    "past_life": "past_life",
    "reincarnated_child": "reincarnated_childhood",
    "reincarnated_childhood": "reincarnated_childhood",
    "转生幼年": "reincarnated_childhood",
    "转世幼年": "reincarnated_childhood",
    "转世童年": "reincarnated_childhood",
    "重生童年": "reincarnated_childhood",
    "reincarnated childhood": "reincarnated_childhood",
    "childhood": "childhood",
    "幼年": "childhood",
    "adolescence": "adolescence",
    "少年": "adolescence",
    "adulthood": "adulthood",
    "成年": "adulthood",
}

AGE_STAGE_ALIASES = {
    "child": "childhood",
    "children": "childhood",
    "childhood": "childhood",
    "幼儿": "childhood",
    "幼年": "childhood",
    "儿童": "childhood",
    "童年": "childhood",
    "adolescent": "adolescence",
    "adolescence": "adolescence",
    "少年": "adolescence",
    "青少年": "adolescence",
    "young adult": "adulthood",
    "young_adult": "adulthood",
    "adult": "adulthood",
    "adulthood": "adulthood",
    "青年": "adulthood",
    "成年": "adulthood",
    "elderly": "elderly",
    "old age": "elderly",
    "老年": "elderly",
}

EXPERIENCED_AGE_MARKERS = (
    "实际年龄",
    "两世为人",
    "成年人心态",
    "成人心态",
    "心理年龄",
    "心智年龄",
)

LIFE_PHASE_LABELS = {
    "past_life": "前世",
    "reincarnated_childhood": "转生幼年",
    "childhood": "幼年",
    "adolescence": "少年期",
    "adulthood": "成年期",
}


@dataclass(frozen=True)
class NormalizedVisualFact:
    field_path: str
    value: Any


def canonical_field_path(field_path: str, *, character_name: str | None = None) -> str:
    path = field_path.strip()
    if character_name:
        prefix = f"{character_name}."
        if path.startswith(prefix):
            path = path[len(prefix) :]
    path = FIELD_PATH_ALIASES.get(path, path)
    if path.startswith("appearance."):
        candidate = path.removeprefix("appearance.")
        candidate = FIELD_PATH_ALIASES.get(candidate, candidate)
        if candidate == "build":
            return "body.build"
        if candidate.split(".", 1)[0] in VISUAL_FIELD_ROOTS:
            return candidate
    return path


def is_visual_field(field_path: str) -> bool:
    canonical = canonical_field_path(field_path)
    if canonical == "appearance":
        return True
    return canonical.split(".", 1)[0] in VISUAL_FIELD_ROOTS


def visual_category(field_path: str) -> str | None:
    canonical = canonical_field_path(field_path)
    if canonical == "appearance":
        return "综合外观"
    return VISUAL_CATEGORY_LABELS.get(canonical.split(".", 1)[0])


def normalize_life_phase(
    key: str | None, label: str | None
) -> tuple[str | None, str | None]:
    normalized_key = key.strip() if key and key.strip() else None
    normalized_label = label.strip() if label and label.strip() else None
    if normalized_key:
        phase_token = normalized_key.casefold().replace("-", "_")
        normalized_key = LIFE_PHASE_ALIASES.get(
            phase_token, LIFE_PHASE_ALIASES.get(normalized_key, phase_token.replace(" ", "_"))
        )
    elif normalized_label:
        label_token = normalized_label.casefold().replace("-", "_")
        normalized_key = LIFE_PHASE_ALIASES.get(
            label_token, LIFE_PHASE_ALIASES.get(normalized_label)
        )
    if normalized_key in LIFE_PHASE_LABELS:
        normalized_label = LIFE_PHASE_LABELS[normalized_key]
    elif normalized_label is None and normalized_key is not None:
        normalized_label = normalized_key
    return normalized_key, normalized_label


def _flatten_mapping(value: dict[str, Any], prefix: str = "") -> list[tuple[str, Any]]:
    flattened: list[tuple[str, Any]] = []
    for key, item in value.items():
        path = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(item, dict):
            flattened.extend(_flatten_mapping(item, path))
        else:
            flattened.append((path, item))
    return flattened


def _append_unique(
    facts: list[NormalizedVisualFact], field_path: str, value: Any
) -> None:
    candidate = NormalizedVisualFact(field_path=field_path, value=value)
    if candidate not in facts:
        facts.append(candidate)


def _split_appearance_text(value: str) -> tuple[NormalizedVisualFact, ...]:
    facts: list[NormalizedVisualFact] = []

    for token in ("小麦色", "古铜色", "白皙", "苍白", "黝黑", "健康肤色"):
        if token in value:
            _append_unique(facts, "skin.color", token)
            break

    hair_color = re.search(r"(黑色|白色|银色|金色|棕色|红色|蓝色|紫色)(?=.{0,3}发)", value)
    if hair_color:
        _append_unique(facts, "hair.color", hair_color.group(1))
    hair_length = re.search(r"(及腰长发|齐肩发|中长发|长发|短发)", value)
    if hair_length:
        _append_unique(facts, "hair.length", hair_length.group(1))

    for token in ("朴素", "华丽", "简洁", "破旧", "粗布", "整齐"):
        if token in value:
            _append_unique(facts, "clothing.style", token)
            break
    for token in ("干净", "整洁", "脏污", "邋遢"):
        if token in value:
            _append_unique(facts, "cleanliness", token)
            break
    for token in ("瘦小", "纤细", "高大", "魁梧", "健壮", "消瘦", "匀称"):
        if token in value:
            _append_unique(facts, "body.build", token)
            break

    if not facts:
        facts.append(NormalizedVisualFact(field_path="body.description", value=value))
    return tuple(facts)


def normalize_observation_fields(
    field_path: str,
    value: Any,
    *,
    character_name: str | None = None,
    evidence_quote: str | None = None,
) -> tuple[NormalizedVisualFact, ...]:
    canonical = canonical_field_path(field_path, character_name=character_name)
    quote = evidence_quote or ""
    if canonical == "age" and any(marker in quote for marker in EXPERIENCED_AGE_MARKERS):
        canonical = "identity.experienced_age"
    elif canonical == "age_stage" and any(
        marker in quote for marker in EXPERIENCED_AGE_MARKERS
    ):
        canonical = "identity.mental_age_stage"
    if canonical == "age_stage" and isinstance(value, str):
        value = AGE_STAGE_ALIASES.get(value.strip().casefold(), value.strip())
    if canonical == "abilities.innate_soul_power" and value is True:
        value = "先天满魂力"
    if canonical != "appearance":
        return (NormalizedVisualFact(field_path=canonical, value=value),)
    if isinstance(value, dict):
        facts = [
            NormalizedVisualFact(
                field_path=canonical_field_path(f"appearance.{path}"),
                value=item,
            )
            for path, item in _flatten_mapping(value)
        ]
        return tuple(facts) or (
            NormalizedVisualFact(field_path="body.description", value=value),
        )
    if isinstance(value, str):
        return _split_appearance_text(value)
    return (NormalizedVisualFact(field_path="body.description", value=value),)
