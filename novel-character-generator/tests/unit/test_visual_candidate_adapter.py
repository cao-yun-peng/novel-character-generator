from novel_character_generator.application.ports.extraction import (
    VisualCandidateExtractionResult,
    VisualEntityCandidate,
    VisualFactCandidate,
    VisualTemporalSignal,
    VisualTemporalSignalCandidate,
)
from novel_character_generator.application.services.visual_candidate_adapter import (
    adapt_visual_candidates,
    ground_visual_candidates,
)


def _entity(**updates: object) -> VisualEntityCandidate:
    values: dict[str, object] = {
        "local_id": "e1",
        "representative_name": "沈砚",
        "mention_quote": "沈砚",
        "mention_kind": "name",
        "confidence": 0.95,
    }
    values.update(updates)
    return VisualEntityCandidate.model_validate(values)


def _fact(**updates: object) -> VisualFactCandidate:
    values: dict[str, object] = {
        "entity_ref": "e1",
        "field_path": "hair.color",
        "value": "黑色",
        "evidence_quote": "黑发",
        "epistemic_status": "asserted",
        "confidence": 0.9,
    }
    values.update(updates)
    return VisualFactCandidate.model_validate(values)


def test_adapter_locates_v3_evidence_without_provider_offsets() -> None:
    text = "沈砚披着旧青氅，一头黑发束在脑后。"
    candidates = VisualCandidateExtractionResult(
        entities=[_entity()],
        visual_candidates=[_fact()],
    )

    result = adapt_visual_candidates(text, candidates)

    assert [(item.start, item.end, item.text) for item in result.mentions] == [(0, 2, "沈砚")]
    assert len(result.observations) == 1
    observation = result.observations[0]
    assert text[observation.start : observation.end] == "黑发"
    assert observation.field_path == "hair.color"
    assert result.warnings == []


def test_adapter_rejects_nonvisual_noncanonical_and_inferred_candidates() -> None:
    text = "沈砚黑发，擅长剑术。"
    candidates = VisualCandidateExtractionResult(
        entities=[_entity()],
        visual_candidates=[
            _fact(field_path="abilities.sword", evidence_quote="擅长剑术"),
            _fact(field_path="appearance.hair_color"),
            _fact(epistemic_status="inferred"),
        ],
    )

    result = adapt_visual_candidates(text, candidates)

    assert result.observations == []
    assert len(result.warnings) == 3


def test_adapter_rejects_ambiguous_evidence_instead_of_guessing() -> None:
    text = "白衣，沈砚，白衣。"
    candidates = VisualCandidateExtractionResult(
        entities=[_entity()],
        visual_candidates=[_fact(field_path="clothing.color", value="白色", evidence_quote="白衣")],
    )

    result = adapt_visual_candidates(text, candidates)

    assert result.observations == []
    assert result.warnings == ["rejected_visual_candidate:0:evidence_ambiguous"]


def test_adapter_preserves_explicit_life_phase_signal() -> None:
    text = "前世的沈砚留着黑发。"
    candidates = VisualCandidateExtractionResult(
        entities=[_entity()],
        visual_candidates=[
            _fact(
                temporal_signals=[
                    VisualTemporalSignal(
                        kind="life_phase",
                        label="前世",
                        evidence_quote="前世",
                    )
                ]
            )
        ],
    )

    result = adapt_visual_candidates(text, candidates)

    assert result.observations[0].life_phase_key == "past_life"
    assert result.observations[0].life_phase_label == "前世"
    grounded = ground_visual_candidates(text, candidates, mention_id_prefix="run:chunk")
    assert grounded.temporal_signals[0].kind == "life_phase"
    assert grounded.temporal_signals[0].fact_candidate_key == grounded.facts[0].candidate_key


def test_adapter_preserves_top_level_and_non_phase_temporal_signals() -> None:
    text = "梦中的沈砚留着黑发。三年后，他已经白发。"
    candidates = VisualCandidateExtractionResult(
        entities=[_entity()],
        visual_candidates=[
            _fact(
                temporal_signals=[
                    VisualTemporalSignal(
                        kind="presentation",
                        label="梦中",
                        evidence_quote="梦中",
                    )
                ]
            )
        ],
        temporal_signals=[
            VisualTemporalSignalCandidate(
                entity_ref="e1",
                kind="time_jump",
                label="三年后",
                evidence_quote="三年后",
                confidence=0.93,
            )
        ],
    )

    result = ground_visual_candidates(text, candidates, mention_id_prefix="run:chunk")

    assert {signal.kind for signal in result.temporal_signals} == {
        "presentation",
        "time_jump",
    }
    time_jump = next(signal for signal in result.temporal_signals if signal.kind == "time_jump")
    assert time_jump.mention_id == result.mentions[0].mention_id
    assert time_jump.fact_candidate_key is None


def test_adapter_rejects_rank_as_age_and_invalid_field_semantics() -> None:
    text = "沈砚达到二十六级，掌中青光闪烁，狼爪掠过地面。"
    candidates = VisualCandidateExtractionResult(
        entities=[_entity()],
        visual_candidates=[
            _fact(field_path="clothing.color", value="青色", evidence_quote="青光"),
            _fact(field_path="distinctive_marks.scar", value="狼爪痕", evidence_quote="狼爪"),
        ],
        temporal_signals=[
            VisualTemporalSignalCandidate(
                entity_ref="e1",
                kind="age",
                label="二十六级",
                evidence_quote="二十六级",
                confidence=0.92,
            )
        ],
    )

    result = ground_visual_candidates(text, candidates, mention_id_prefix="run:chunk")

    assert result.facts == []
    assert result.temporal_signals == []
    assert "rejected_visual_candidate:0:clothing_color_without_garment" in result.warnings
    assert "rejected_visual_candidate:1:scar_without_scar_evidence" in result.warnings
    assert "ignored_temporal_signal:top:0:age:invalid_age_semantics" in result.warnings


def test_adapter_normalizes_cleanliness_and_preserves_generic_special_bucket() -> None:
    text = "沈砚穿着脏污长袍，发动异形姿态。"
    candidates = VisualCandidateExtractionResult(
        entities=[_entity()],
        visual_candidates=[
            _fact(field_path="clothing.condition", value="脏污", evidence_quote="脏污长袍")
        ],
        temporal_signals=[
            VisualTemporalSignalCandidate(
                entity_ref="e1",
                kind="other",
                label="异形姿态",
                evidence_quote="异形姿态",
                confidence=0.88,
            )
        ],
    )

    result = ground_visual_candidates(text, candidates, mention_id_prefix="run:chunk")

    assert result.facts[0].field_path == "cleanliness"
    assert result.temporal_signals[0].kind == "other"
    assert "normalized_visual_candidate:0:clothing.condition:cleanliness" in result.warnings


def test_adapter_repairs_cross_dimension_fields_and_rejects_hair_as_eye_color() -> None:
    text = "沈砚伸出稚嫩的小手，眼中闪过亮光，留着黑色短发，双手探出利爪。"
    candidates = VisualCandidateExtractionResult(
        entities=[_entity()],
        visual_candidates=[
            _fact(field_path="face.hands", value="稚嫩的小手", evidence_quote="稚嫩的小手"),
            _fact(field_path="face.eye_color", value="闪亮", evidence_quote="眼中闪过亮光"),
            _fact(field_path="face.eye_color", value="黑色", evidence_quote="黑色短发"),
            _fact(field_path="accessories.gloves", value="利爪", evidence_quote="双手探出利爪"),
        ],
    )

    result = ground_visual_candidates(text, candidates, mention_id_prefix="run:chunk")

    assert [item.field_path for item in result.facts] == [
        "body.hands",
        "face.eyes",
        "distinctive_marks.claws",
    ]
    assert "rejected_visual_candidate:2:eye_color_without_eye_evidence" in result.warnings


def test_adapter_ignores_bare_condition_mislabeled_as_transformation() -> None:
    text = "沈砚全身赤裸。"
    candidates = VisualCandidateExtractionResult(
        entities=[_entity()],
        visual_candidates=[
            _fact(
                field_path="clothing.coverage",
                value="全身赤裸",
                evidence_quote="全身赤裸",
                temporal_signals=[
                    VisualTemporalSignal(
                        kind="transformation",
                        label="赤裸",
                        evidence_quote="全身赤裸",
                    )
                ],
            )
        ],
    )

    result = ground_visual_candidates(text, candidates, mention_id_prefix="run:chunk")

    assert len(result.facts) == 1
    assert result.temporal_signals == []
    assert (
        "ignored_temporal_signal:0:transformation:invalid_transformation_semantics"
        in result.warnings
    )
