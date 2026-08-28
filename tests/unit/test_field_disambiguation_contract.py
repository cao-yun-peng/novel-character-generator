import json

import pytest
from pydantic import ValidationError

from novel_character_generator.application.ports.field_disambiguation import (
    FieldDisambiguationModelDecision,
    FieldDisambiguationModelMapping,
    FieldDisambiguationModelOutput,
)
from novel_character_generator.domain.policies.visual_field_catalog import (
    VISUAL_FIELD_CATALOG,
    VISUAL_FIELD_CATALOG_VERSION,
    VISUAL_FIELD_PATHS,
    is_catalog_field,
    visual_field_catalog_payload,
)


def test_m2_v1_catalog_is_exact_unique_and_string_only() -> None:
    assert VISUAL_FIELD_CATALOG_VERSION == "visual-field-catalog-v1"
    assert len(VISUAL_FIELD_CATALOG) == len(VISUAL_FIELD_PATHS)
    assert all(item.value_type == "string" for item in VISUAL_FIELD_CATALOG)
    assert all("*" not in item.field_path for item in VISUAL_FIELD_CATALOG)
    assert is_catalog_field("hair.color")
    assert is_catalog_field("clothing.condition")
    assert not is_catalog_field("face")
    assert not is_catalog_field("face.expression")
    assert not is_catalog_field("age.age")
    assert not is_catalog_field("accessories.book")
    assert set(visual_field_catalog_payload()[0]) == {
        "field_path",
        "value_type",
        "description",
    }


def test_m2_model_wire_excludes_code_generated_fields_and_typed_values() -> None:
    rendered = json.dumps(FieldDisambiguationModelOutput.model_json_schema())
    for field in ("fact_id", "mapping_id", "semantic_unit_id", "evidence_quote"):
        assert field not in rendered
    assert "fact_index" in rendered
    assert "semantic_unit_index" in rendered
    normalized_schema = FieldDisambiguationModelMapping.model_json_schema()["properties"][
        "normalized_value"
    ]
    assert normalized_schema["type"] == "string"


@pytest.mark.parametrize(
    ("decision", "reason", "mapping_count"),
    [
        ("map", "explicit_atomic_mapping", 0),
        ("defer", "missing_semantic_context", 1),
        ("reject", "ambiguous_semantic_decomposition", 0),
    ],
)
def test_m2_wire_decision_shape_fails_closed(
    decision: str,
    reason: str,
    mapping_count: int,
) -> None:
    mappings = [
        {
            "semantic_unit_index": 0,
            "referent_kind": "garment",
            "referent_quote": "蓝衣",
            "field_path": "clothing.color",
            "normalized_value": "蓝色",
        }
    ] * mapping_count
    with pytest.raises(ValidationError):
        FieldDisambiguationModelDecision.model_validate(
            {
                "fact_index": 0,
                "decision": decision,
                "mappings": mappings,
                "reason_code": reason,
            }
        )


def test_m2_wire_rejects_null_non_character_referent() -> None:
    with pytest.raises(ValidationError, match="null_referent_requires_whole_character"):
        FieldDisambiguationModelMapping(
            semantic_unit_index=0,
            referent_kind="garment",
            referent_quote=None,
            field_path="clothing.type",
            normalized_value="长袍",
        )
