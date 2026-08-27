from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from novel_character_generator.application.ports.extraction import (
    VisualCandidateExtractionResult,
)
from novel_character_generator.application.services.visual_candidate_adapter import (
    ground_visual_candidates,
)
from novel_character_generator.domain.policies.grounding import locate_evidence_span

BASELINE_PATH = Path(__file__).parents[1] / "evaluation" / "r1_quality_regression_v1.json"


def _baseline() -> dict[str, Any]:
    return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))


def _case(case_id: str) -> dict[str, Any]:
    return next(item for item in _baseline()["cases"] if item["id"] == case_id)


def _ground(case_id: str):  # type: ignore[no-untyped-def]
    case = _case(case_id)
    candidates = VisualCandidateExtractionResult.model_validate(case["provider_output"])
    return ground_visual_candidates(
        case["text"],
        candidates,
        mention_id_prefix=f"r1-baseline:{case_id}",
    )


def test_r1_quality_baseline_scope_and_states_are_frozen() -> None:
    baseline = _baseline()
    cases = {item["id"]: item for item in baseline["cases"]}

    assert baseline["version"] == "v1"
    assert set(cases) == {
        "descriptor-mention-is-preserved",
        "nested-age-path-is-normalized",
        "book-is-not-clothing",
        "unique-one-character-omission-is-repaired",
        "ambiguous-one-character-omission-is-rejected",
        "semantic-substitution-is-not-repaired",
        "exact-source-quote-is-preserved",
    }
    assert {item["layer"] for item in cases.values()} == {
        "schema-and-grounding",
        "field-gate",
        "evidence-locator",
    }
    assert sum(item["baseline_state"] == "xfail" for item in cases.values()) == 5
    assert sum(item["baseline_state"] == "pass" for item in cases.values()) == 2


@pytest.mark.xfail(
    strict=True,
    reason="R1 red baseline: descriptor is not yet part of the extraction contract",
)
def test_r1_descriptor_mention_is_preserved_for_r2_without_identity_binding() -> None:
    result = _ground("descriptor-mention-is-preserved")

    assert [mention.mention_kind for mention in result.mentions] == ["descriptor"]
    assert [fact.field_path for fact in result.facts] == ["accessories.earrings"]


@pytest.mark.xfail(
    strict=True,
    reason="R1 red baseline: age.age is not yet a safe field alias",
)
def test_r1_nested_age_path_is_normalized_to_canonical_age() -> None:
    case = _case("nested-age-path-is-normalized")
    result = _ground(case["id"])

    assert [fact.field_path for fact in result.facts] == case["expected"]["field_paths"]
    assert case["expected"]["warning_contains"] in result.warnings


@pytest.mark.xfail(
    strict=True,
    reason="R1 red baseline: clothing.type does not yet require garment evidence",
)
def test_r1_non_garment_object_is_rejected_from_clothing_type() -> None:
    case = _case("book-is-not-clothing")
    result = _ground(case["id"])

    assert [fact.field_path for fact in result.facts] == case["expected"]["field_paths"]
    assert case["expected"]["warning_contains"] in result.warnings


@pytest.mark.xfail(
    strict=True,
    reason="R1 red baseline: narrow one-character evidence repair is not implemented",
)
def test_r1_unique_one_character_omission_repairs_to_exact_source_quote() -> None:
    case = _case("unique-one-character-omission-is-repaired")
    location = locate_evidence_span(case["text"], case["quote"])

    assert location.status == case["expected"]["status"]
    assert location.source_quote == case["expected"]["source_quote"]


@pytest.mark.xfail(
    strict=True,
    reason="R1 red baseline: ambiguous narrow repairs are not classified yet",
)
def test_r1_ambiguous_one_character_omission_remains_unresolved() -> None:
    case = _case("ambiguous-one-character-omission-is-rejected")
    location = locate_evidence_span(case["text"], case["quote"])

    assert location.status == case["expected"]["status"]
    assert location.source_quote is None


@pytest.mark.parametrize(
    "case_id",
    ["semantic-substitution-is-not-repaired", "exact-source-quote-is-preserved"],
)
def test_r1_existing_evidence_safety_boundaries_remain_green(case_id: str) -> None:
    case = _case(case_id)
    location = locate_evidence_span(case["text"], case["quote"])

    assert location.status == case["expected"]["status"]
    assert location.source_quote == case["expected"]["source_quote"]
