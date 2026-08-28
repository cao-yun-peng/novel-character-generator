import pytest
from pydantic import ValidationError

from novel_character_generator.application.ports.local_observation import (
    DEFAULT_COARSE_VISUAL_FAMILIES,
    LocalObservationDiscoveryInput,
    LocalObservationDiscoveryResult,
)
from novel_character_generator.application.services.local_observation_service import (
    LocalObservationContractError,
    validate_local_observation_output,
)


def _request(text: str = "沈砚留着黑色短发。") -> LocalObservationDiscoveryInput:
    return LocalObservationDiscoveryInput(
        schema_version="local-observation-discovery-input-v1.1",
        chunk_id="chunk-1",
        chunk_text=text,
        previous_tail="上一段写过银发。",
        allowed_coarse_families=list(DEFAULT_COARSE_VISUAL_FAMILIES),
    )


def _valid_payload() -> dict[str, object]:
    return {
        "schema_version": "local-observation-discovery-v1.1",
        "chunk_id": "chunk-1",
        "entities": [
            {
                "local_entity_id": "e1",
                "mention_quote": "沈砚",
                "mention_kind": "explicit_name",
                "representative_name": "沈砚",
            }
        ],
        "facts": [
            {
                "local_fact_id": "f1",
                "entity_ref": "e1",
                "evidence_quote": "黑色短发",
                "raw_proposition": "沈砚留着黑色短发",
                "coarse_family": "hair",
                "epistemic_status": "asserted",
            }
        ],
        "temporal_signals": [],
        "unresolved_items": [],
    }


def test_m1_schema_keeps_raw_semantics_and_requires_complete_collections() -> None:
    schema = LocalObservationDiscoveryResult.model_json_schema()
    assert set(schema["required"]) == {
        "schema_version",
        "chunk_id",
        "entities",
        "facts",
        "temporal_signals",
        "unresolved_items",
    }
    rendered = str(schema)
    assert "raw_proposition" in rendered
    assert "coarse_family" in rendered
    assert "field_path" not in rendered
    assert "confidence" not in rendered
    assert "character_id" not in rendered

    incomplete = _valid_payload()
    incomplete.pop("unresolved_items")
    with pytest.raises(ValidationError):
        LocalObservationDiscoveryResult.model_validate(incomplete)


def test_m1_schema_rejects_unknown_refs_and_cross_owner_signal() -> None:
    dangling = _valid_payload()
    dangling["facts"][0]["entity_ref"] = "e2"  # type: ignore[index]
    with pytest.raises(ValidationError, match="unknown_local_entity_ref:e2"):
        LocalObservationDiscoveryResult.model_validate(dangling)

    mismatched = _valid_payload()
    mismatched["entities"].append(  # type: ignore[union-attr]
        {
            "local_entity_id": "e2",
            "mention_quote": "他",
            "mention_kind": "pronoun",
            "representative_name": "他",
        }
    )
    mismatched["temporal_signals"] = [
        {
            "local_signal_id": "t1",
            "entity_ref": "e2",
            "fact_ref": "f1",
            "evidence_quote": "黑色短发",
            "signal_kind": "presentation",
            "raw_label": "当前外观",
        }
    ]
    with pytest.raises(ValidationError, match="temporal_signal_owner_mismatch"):
        LocalObservationDiscoveryResult.model_validate(mismatched)


def test_server_validation_accepts_source_backed_output() -> None:
    output = LocalObservationDiscoveryResult.model_validate(_valid_payload())
    assert validate_local_observation_output(_request(), output) is output


def test_server_validation_rejects_previous_tail_or_invented_quote() -> None:
    payload = _valid_payload()
    payload["facts"][0]["evidence_quote"] = "银发"  # type: ignore[index]
    output = LocalObservationDiscoveryResult.model_validate(payload)
    with pytest.raises(
        LocalObservationContractError,
        match="local_observation_quote_not_in_chunk:fact",
    ):
        validate_local_observation_output(_request(), output)


def test_server_validation_rejects_unused_entity_and_fact_unresolved_double_write() -> None:
    unused = _valid_payload()
    unused["entities"].append(  # type: ignore[union-attr]
        {
            "local_entity_id": "e2",
            "mention_quote": "沈砚",
            "mention_kind": "explicit_name",
            "representative_name": "沈砚",
        }
    )
    with pytest.raises(LocalObservationContractError, match="unused_entity:e2"):
        validate_local_observation_output(
            _request(), LocalObservationDiscoveryResult.model_validate(unused)
        )

    duplicate = _valid_payload()
    duplicate["unresolved_items"] = [
        {
            "local_item_id": "u1",
            "entity_ref": "e1",
            "evidence_quote": "黑色短发",
            "raw_proposition": "沈砚留着黑色短发",
            "reason_code": "ambiguous_local_scope",
        }
    ]
    with pytest.raises(
        LocalObservationContractError,
        match="local_observation_asserted_unresolved_double_write",
    ):
        validate_local_observation_output(
            _request(), LocalObservationDiscoveryResult.model_validate(duplicate)
        )
