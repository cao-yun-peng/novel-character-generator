from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

QUERY_PLAN_VERSION = "visual-query-plan-v1"
FIELD_GAP_POLICY_VERSION = "visual-field-gap-v1"

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
