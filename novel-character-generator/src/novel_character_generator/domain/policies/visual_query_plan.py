from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

QUERY_PLAN_VERSION = "visual-query-plan-v1"
FIELD_GAP_POLICY_VERSION = "visual-field-gap-v2"

FIELD_GROUPS: dict[str, tuple[tuple[str, ...], str]] = {
    "hair": (
        ("头发", "发色", "发型", "长发", "短发", "束发", "鬓发", "凌乱"),
        "描写该角色发型轮廓、头发颜色、长度、束发方式或凌乱状态的段落",
    ),
    "face": (
        ("面容", "脸型", "五官", "眼睛", "瞳色", "眉", "鼻", "嘴唇", "痣"),
        "描写该角色面部轮廓、五官、瞳色或先天面部标记的段落",
    ),
    "body": (
        ("身形", "体型", "身高", "瘦小", "纤细", "魁梧", "健壮", "肤色"),
        "描写该角色身高、体型、身形轮廓、肤色或年龄外观的段落",
    ),
    "clothing": (
        ("衣着", "服装", "长袍", "外套", "斗篷", "裙", "甲", "鞋", "颜色"),
        "描写该角色服装类型、材质、颜色、层次或整洁状态的段落",
    ),
    "accessories": (
        ("配饰", "首饰", "耳饰", "项链", "发饰", "腰饰", "玉佩", "眼镜"),
        "描写该角色佩戴的首饰、发饰、腰饰、眼镜或其他可见配件的段落",
    ),
    "marks_injuries": (
        ("伤", "疤", "伤痕", "烫伤", "纹身", "胎记", "显著标记"),
        "描写该角色伤势、疤痕、胎记、纹身或其他显著身体标记的段落",
    ),
    "disguise_cleanliness": (
        ("伪装", "易容", "面具", "污渍", "灰尘", "血迹", "整洁", "邋遢"),
        "描写该角色伪装、易容、面具、污渍或整洁状态的段落",
    ),
}

CORE_FIELD_GROUPS = frozenset({"hair", "face", "body", "clothing"})

FIELD_GROUP_DIMENSIONS: dict[str, dict[str, tuple[str, ...]]] = {
    "hair": {
        "color": ("hair.color",),
        "form": ("hair.length", "hair.style", "hair.texture", "hair.cut"),
    },
    "face": {
        "shape": ("face.shape", "face.description", "face.contour"),
        "eyes": ("face.eye_shape", "face.eye_color", "face.eyes"),
        "features": (
            "face.eyebrows",
            "face.nose",
            "face.mouth",
            "face.lips",
            "face.distinctive_mark",
        ),
    },
    "body": {
        "age": ("age", "age_stage"),
        "build": ("body.build", "body.height", "body.description"),
        "skin": ("skin.color", "skin.description"),
    },
    "clothing": {
        "form": ("clothing.style", "clothing.type", "clothing.outerwear"),
        "color_or_material": ("clothing.color", "clothing.material"),
    },
    "accessories": {"presence": ("accessory.", "accessories.")},
    "marks_injuries": {
        "presence_or_absence": (
            "injury.",
            "injuries.",
            "distinctive_marks.",
            "face.injury",
            "face.distinctive_mark",
        )
    },
    "disguise_cleanliness": {
        "state": ("disguise.", "cleanliness", "cleanliness.")
    },
}

FIELD_GROUP_REQUIRED_SCORES = {
    "hair": 1.0,
    "face": 2 / 3,
    "body": 2 / 3,
    "clothing": 1.0,
    "accessories": 1.0,
    "marks_injuries": 1.0,
    "disguise_cleanliness": 1.0,
}


def _matches_dimension(field_path: str, patterns: tuple[str, ...]) -> bool:
    return any(
        field_path == pattern or (pattern.endswith(".") and field_path.startswith(pattern))
        for pattern in patterns
    )


def score_visual_field_group(
    field_group: str, observed_field_paths: set[str]
) -> tuple[float, float, tuple[str, ...]]:
    dimensions = FIELD_GROUP_DIMENSIONS[field_group]
    missing = tuple(
        dimension
        for dimension, patterns in dimensions.items()
        if not any(_matches_dimension(path, patterns) for path in observed_field_paths)
    )
    score = (len(dimensions) - len(missing)) / len(dimensions)
    return score, FIELD_GROUP_REQUIRED_SCORES[field_group], missing


def resolve_requested_life_phase(
    requested: str | None,
    *,
    phase_age_stages: dict[str, set[str]],
    normalized_age_stage: str | None,
) -> str | None:
    if requested is None or not requested.strip():
        return None
    token = requested.strip()
    if normalized_age_stage is None:
        return token
    candidates = sorted(
        phase
        for phase, age_stages in phase_age_stages.items()
        if normalized_age_stage in age_stages
    )
    if len(candidates) > 1:
        raise ValueError("ambiguous_life_phase")
    return candidates[0] if candidates else token


def observation_applies_to_phase(
    observation_phase: str | None, requested_phase: str | None
) -> bool:
    if requested_phase is None:
        return True
    # Unscoped facts are not silently promoted across narrative phases. Stable
    # cross-phase identity belongs in an approved RenderProfile instead.
    return observation_phase == requested_phase


def visual_field_group(field_path: str) -> str | None:
    path = field_path.strip()
    root = path.split(".", 1)[0]
    if root == "hair":
        return "hair"
    if root == "face" and path not in {"face.injury", "face.distinctive_mark"}:
        return "face"
    if root in {"body", "skin", "age", "age_stage"}:
        return "body"
    if root == "clothing":
        return "clothing"
    if root in {"accessory", "accessories"}:
        return "accessories"
    if root in {"injury", "injuries", "distinctive_marks"} or path in {
        "face.injury",
        "face.distinctive_mark",
    }:
        return "marks_injuries"
    if root in {"disguise", "cleanliness"}:
        return "disguise_cleanliness"
    return None


@dataclass(frozen=True)
class VisualQueryPlan:
    version: str
    canonical_name: str
    aliases: tuple[str, ...]
    life_phase_key: str | None
    field_groups: tuple[str, ...]
    entity_terms: tuple[str, ...]
    field_terms: tuple[str, ...]
    queries: tuple[dict[str, str], ...]
    max_provider_calls: int
    context_budget_tokens: int

    def as_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "canonical_name": self.canonical_name,
            "aliases": list(self.aliases),
            "life_phase_key": self.life_phase_key,
            "field_groups": list(self.field_groups),
            "entity_terms": list(self.entity_terms),
            "field_terms": list(self.field_terms),
            "queries": list(self.queries),
            "max_provider_calls": self.max_provider_calls,
            "context_budget_tokens": self.context_budget_tokens,
        }

    @property
    def fingerprint(self) -> str:
        payload = json.dumps(
            self.as_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        return hashlib.sha256(payload.encode()).hexdigest()


def build_visual_query_plan(
    *,
    canonical_name: str,
    aliases: list[str],
    field_groups: list[str],
    life_phase_key: str | None,
    max_provider_calls: int,
    context_budget_tokens: int,
) -> VisualQueryPlan:
    normalized_groups = tuple(dict.fromkeys(group.strip() for group in field_groups))
    unknown = sorted(set(normalized_groups) - FIELD_GROUPS.keys())
    if unknown:
        raise ValueError(f"unsupported_visual_field_groups:{','.join(unknown)}")
    if not normalized_groups:
        raise ValueError("visual_field_groups_required")
    normalized_aliases = tuple(
        item
        for item in dict.fromkeys(alias.strip() for alias in aliases)
        if item and item != canonical_name
    )
    entity_terms = (canonical_name, *normalized_aliases)
    field_terms = tuple(
        dict.fromkeys(
            term for group in normalized_groups for term in FIELD_GROUPS[group][0]
        )
    )
    phase = life_phase_key.strip() if life_phase_key and life_phase_key.strip() else None
    phase_terms = (phase,) if phase else ()
    identity_query = " ".join((*entity_terms, "外貌", "形象", *phase_terms))
    queries: list[dict[str, str]] = [
        {"kind": "entity_identity", "text": identity_query},
    ]
    for group in normalized_groups:
        terms, semantic = FIELD_GROUPS[group]
        queries.append(
            {
                "kind": f"entity_field:{group}",
                "text": " ".join((*entity_terms, *terms, *phase_terms)),
            }
        )
        queries.append({"kind": f"semantic_field:{group}", "text": semantic})
    if phase:
        queries.append(
            {
                "kind": "life_phase",
                "text": f"{canonical_name} 在{phase}阶段的年龄、外貌和服饰变化",
            }
        )
    return VisualQueryPlan(
        version=QUERY_PLAN_VERSION,
        canonical_name=canonical_name,
        aliases=normalized_aliases,
        life_phase_key=phase,
        field_groups=normalized_groups,
        entity_terms=entity_terms,
        field_terms=field_terms,
        queries=tuple(queries),
        max_provider_calls=max_provider_calls,
        context_budget_tokens=context_budget_tokens,
    )
