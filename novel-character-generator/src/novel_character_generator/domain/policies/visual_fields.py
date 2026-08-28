from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

EXTRACTION_SCHEMA_VERSION = "visual-observation-v3.4"

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
    "age.age": "age",
    "age.age_stage": "age_stage",
    "face.hands": "body.hands",
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


def normalize_age_stage(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    token = value.strip().casefold().replace("-", "_").replace(" ", "_")
    return AGE_STAGE_ALIASES.get(token, token)


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

_AGE_MARKERS = (
    "岁",
    "周岁",
    "年龄",
    "年纪",
    "年岁",
    "旬",
    "years old",
    "year old",
    "aged ",
    "age ",
)
_NON_AGE_RANK_MARKERS = (
    "等级",
    "级",
    "品阶",
    "阶位",
    "段位",
    "境界",
    "level",
    "rank",
    "tier",
)
_CLOTHING_MARKERS = (
    "衣",
    "袍",
    "裙",
    "衫",
    "装",
    "服",
    "裤",
    "鞋",
    "靴",
    "披风",
    "斗篷",
    "甲",
    "帽",
    "袖",
    "褂",
    "氅",
    "袄",
    "裘",
    "袜",
    "铠",
    "garment",
    "clothes",
    "clothing",
    "shirt",
    "robe",
    "dress",
    "coat",
    "cloak",
    "armor",
    "trousers",
    "pants",
    "boots",
    "shoes",
)
_NON_CLOTHING_OBJECT_MARKERS = (
    "书",
    "书籍",
    "卷轴",
    "剑",
    "刀",
    "枪",
    "矛",
    "弓",
    "箭",
    "斧",
    "锤",
    "武器",
    "丹药",
    "药丸",
    "药剂",
    "药瓶",
    "medicine",
    "potion",
    "book",
    "scroll",
    "sword",
    "blade",
    "weapon",
)
_NON_WORN_ACCESSORY_FIELD_MARKERS = (
    "held",
    "vehicle",
    "weapon",
    "book",
    "medicine",
    "tool",
    "手持",
    "坐骑",
    "武器",
    "书籍",
    "药物",
    "工具",
)
_HELD_OR_RIDDEN_MARKERS = (
    "手持",
    "拿着",
    "握着",
    "提着",
    "捧着",
    "怀抱",
    "骑着",
    "坐骑",
    "held",
    "holding",
    "carrying",
    "riding",
)
_WORN_INSIGNIA_FIELD_MARKERS = ("insignia", "badge", "emblem", "徽章", "徽记", "标志")
_INSIGNIA_EVIDENCE_MARKERS = (
    "绘",
    "绣",
    "纹在衣",
    "印在衣",
    "徽",
    "图案",
    "标志",
    "badge",
    "emblem",
    "embroider",
    "printed on",
)
_CANONICAL_CLOTHING_FIELDS = frozenset(
    {
        "clothing.type",
        "clothing.color",
        "clothing.material",
        "clothing.condition",
        "clothing.coverage",
        "clothing.footwear",
        "clothing.outerwear",
        "clothing.style",
    }
)
_COVERAGE_MARKERS = (
    "赤裸",
    "裸露",
    "露出",
    "遮住",
    "包裹",
    "covered",
    "exposed",
    "bare",
    "naked",
)
_SCAR_MARKERS = (
    "疤",
    "伤疤",
    "疤痕",
    "瘢痕",
    "旧伤",
    "scar",
)
_CLOTHING_STYLE_MARKERS = (
    "朴素",
    "华丽",
    "简洁",
    "简约",
    "正式",
    "休闲",
    "plain",
    "ornate",
    "formal",
    "casual",
)
_CLEANLINESS_MARKERS = (
    "干净",
    "整洁",
    "脏污",
    "污渍",
    "邋遢",
    "clean",
    "tidy",
    "dirty",
    "stained",
)
_EYE_MARKERS = ("眼", "眸", "瞳", "目光", "视线", "iris", "eye", "gaze")
_COMPLEXION_MARKERS = (
    "面色",
    "脸色",
    "肤色",
    "皮肤",
    "苍白",
    "惨白",
    "红润",
    "蜡黄",
    "暗黄",
    "黝黑",
    "白皙",
    "绯红",
    "泛红",
    "红晕",
    "complexion",
    "skin tone",
)
_FACE_PHYSICAL_MARKERS = (
    "脸",
    "面容",
    "容貌",
    "面庞",
    "脸庞",
    "五官",
    "轮廓",
    "face",
    "facial",
)
_TRANSIENT_EXPRESSION_MARKERS = (
    "笑",
    "哭",
    "皱眉",
    "嫉妒",
    "愤怒",
    "落寞",
    "表情",
    "神色",
    "神情",
    "smile",
    "laugh",
    "frown",
    "expression",
)
_AESTHETIC_DEMEANOR_MARKERS = (
    "美丽",
    "漂亮",
    "英俊",
    "俊美",
    "清秀",
    "冷艳",
    "魅力",
    "吸引",
    "漠然",
    "颓废",
    "beautiful",
    "handsome",
    "attractive",
    "charming",
)
_TATTOO_MARKERS = (
    "纹身",
    "刺青",
    "文身",
    "墨纹",
    "烙印",
    "tattoo",
    "inked",
)
_APPEARANCE_INFERENCE_MARKERS = (
    "看起来",
    "看上去",
    "瞧着",
    "仿佛",
    "似乎",
    "宛如",
    "像是",
    "looks like",
    "appears to be",
    "seems",
)
_COLOR_MARKERS = (
    "黑",
    "白",
    "灰",
    "红",
    "赤",
    "黄",
    "棕",
    "褐",
    "蓝",
    "青",
    "绿",
    "紫",
    "金",
    "银",
    "black",
    "white",
    "gray",
    "grey",
    "red",
    "yellow",
    "brown",
    "blue",
    "green",
    "purple",
    "gold",
    "silver",
)
_CLAW_MARKERS = ("爪", "利爪", "claw", "talon")
_TRANSFORMATION_MARKERS = (
    "变身",
    "变形",
    "变成",
    "变为",
    "变化",
    "形态",
    "附体",
    "兽化",
    "魔化",
    "化身",
    "膨胀",
    "长出",
    "探出",
    "出现",
    "覆盖",
    "收回",
    "解除",
    "激活",
    "展开",
    "部署",
    "transform",
    "shapeshift",
    "possess",
    "powered form",
    "activate",
    "deploy",
    "revert",
)


def is_plausible_age_signal(label: str, evidence_quote: str) -> bool:
    """Accept explicit age evidence and reject rank, level, and plain-duration lookalikes."""

    text = f"{label} {evidence_quote}".strip().casefold()
    has_age_marker = any(marker in text for marker in _AGE_MARKERS)
    if not has_age_marker:
        return False
    if any(marker in text for marker in _NON_AGE_RANK_MARKERS) and not any(
        marker in text for marker in ("岁", "年龄", "年纪", "years old", "year old")
    ):
        return False
    return True


def is_plausible_transformation_signal(label: str, evidence_quote: str) -> bool:
    """Reject ordinary temporary conditions mislabeled as a form transformation."""

    text = f"{label} {evidence_quote}".strip().casefold()
    return any(marker in text for marker in _TRANSFORMATION_MARKERS)


def transformation_applies_to_visual_fact(
    field_path: str,
    value: Any,
    evidence_quote: str,
) -> bool:
    """Narrow a mention-level form signal to facts that explicitly describe the changed form."""

    text = f"{value} {evidence_quote}".casefold()
    if field_path in {"age", "age_stage"}:
        return False
    return any(marker in text for marker in _TRANSFORMATION_MARKERS)


def semantic_visual_field_path(field_path: str, value: Any, evidence_quote: str) -> str:
    """Apply only high-confidence, cross-genre semantic corrections."""

    text = f"{value} {evidence_quote}".casefold()
    if field_path == "clothing.condition":
        if any(marker in text for marker in _CLEANLINESS_MARKERS):
            return "cleanliness"
        if any(marker in text for marker in _CLOTHING_STYLE_MARKERS):
            return "clothing.style"
    if field_path == "clothing.type" and any(
        marker in text for marker in (*_CLOTHING_STYLE_MARKERS, "光鲜", "朴素")
    ):
        return "clothing.style"
    if field_path == "face.eye_color":
        has_eye = any(marker in text for marker in _EYE_MARKERS)
        has_color = any(marker in text for marker in _COLOR_MARKERS)
        if has_eye and not has_color:
            return "face.eyes"
    if field_path == "accessories.gloves" and any(marker in text for marker in _CLAW_MARKERS):
        return "distinctive_marks.claws"
    return field_path


def visual_field_semantic_issue(
    field_path: str,
    value: Any,
    evidence_quote: str,
) -> str | None:
    """Return a stable reason code when a field contradicts its evidence dimension."""

    text = f"{value} {evidence_quote}".casefold()
    value_text = str(value).casefold()
    if field_path == "age":
        if any(marker in text for marker in _APPEARANCE_INFERENCE_MARKERS):
            return "inferred_age"
        if not is_plausible_age_signal(str(value), evidence_quote):
            return "invalid_age_semantics"
    if field_path == "age_stage" and any(
        marker in text for marker in _APPEARANCE_INFERENCE_MARKERS
    ):
        return "inferred_age_stage"
    if field_path == "face.eye_color" and not any(marker in text for marker in _EYE_MARKERS):
        return "eye_color_without_eye_evidence"
    if field_path == "face.eyes" and not any(marker in text for marker in _EYE_MARKERS):
        return "eye_state_without_eye_evidence"
    if field_path == "face.complexion" and not any(
        marker in text for marker in _COMPLEXION_MARKERS
    ):
        return "complexion_without_skin_evidence"
    if field_path == "face.expression":
        return "transient_expression_as_character_fact"
    if field_path == "face.description":
        if not any(marker in text for marker in _FACE_PHYSICAL_MARKERS):
            return "face_description_without_face_evidence"
        if any(marker in text for marker in _TRANSIENT_EXPRESSION_MARKERS):
            return "transient_expression_as_face_description"
        if any(marker in text for marker in _AESTHETIC_DEMEANOR_MARKERS):
            return "aesthetic_impression_as_face_description"
    if field_path.startswith("clothing."):
        if field_path not in _CANONICAL_CLOTHING_FIELDS:
            return "unsupported_clothing_field"
        if any(marker in value_text for marker in _NON_CLOTHING_OBJECT_MARKERS):
            return "non_garment_object_as_clothing"
        if field_path == "clothing.coverage":
            if not any(marker in text for marker in (*_CLOTHING_MARKERS, *_COVERAGE_MARKERS)):
                return "clothing_coverage_without_coverage"
        elif not any(marker in text for marker in _CLOTHING_MARKERS):
            leaf = field_path.removeprefix("clothing.").replace(".", "_")
            return f"clothing_{leaf}_without_garment"
    if field_path.startswith("accessories."):
        leaf = field_path.removeprefix("accessories.").casefold()
        is_worn_insignia = any(
            marker in leaf for marker in _WORN_INSIGNIA_FIELD_MARKERS
        ) and any(marker in text for marker in _INSIGNIA_EVIDENCE_MARKERS)
        if any(marker in leaf for marker in _NON_WORN_ACCESSORY_FIELD_MARKERS):
            return "non_worn_object_as_accessory"
        if not is_worn_insignia and any(
            marker in value_text for marker in _NON_CLOTHING_OBJECT_MARKERS
        ):
            return "non_worn_object_as_accessory"
        if any(marker in text for marker in _HELD_OR_RIDDEN_MARKERS):
            return "held_or_ridden_object_as_accessory"
    if field_path == "distinctive_marks.scar" and not any(
        marker in text for marker in _SCAR_MARKERS
    ):
        return "scar_without_scar_evidence"
    if field_path == "distinctive_marks.tattoo" and not any(
        marker in text for marker in _TATTOO_MARKERS
    ):
        return "tattoo_without_tattoo_evidence"
    return None


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
    if canonical.startswith("age."):
        return False
    return canonical.split(".", 1)[0] in VISUAL_FIELD_ROOTS


def visual_category(field_path: str) -> str | None:
    canonical = canonical_field_path(field_path)
    if canonical == "appearance":
        return "综合外观"
    return VISUAL_CATEGORY_LABELS.get(canonical.split(".", 1)[0])


def normalize_life_phase(key: str | None, label: str | None) -> tuple[str | None, str | None]:
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


def _append_unique(facts: list[NormalizedVisualFact], field_path: str, value: Any) -> None:
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
    elif canonical == "age_stage" and any(marker in quote for marker in EXPERIENCED_AGE_MARKERS):
        canonical = "identity.mental_age_stage"
    if canonical == "age_stage" and isinstance(value, str):
        value = normalize_age_stage(value)
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
        return tuple(facts) or (NormalizedVisualFact(field_path="body.description", value=value),)
    if isinstance(value, str):
        return _split_appearance_text(value)
    return (NormalizedVisualFact(field_path="body.description", value=value),)
