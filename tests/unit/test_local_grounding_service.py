from __future__ import annotations

from novel_character_generator.application.ports.local_grounding import (
    LocalGroundingExecutionRequest,
)
from novel_character_generator.application.ports.local_observation import (
    LocalObservationDiscoveryResult,
    LocalObservationEntity,
    LocalObservationFact,
    LocalObservationTemporalSignal,
    LocalObservationUnresolvedItem,
)
from novel_character_generator.application.services.local_grounding_service import (
    LocalGroundingService,
)


def _entity(*, quote: str = "男子") -> LocalObservationEntity:
    return LocalObservationEntity(
        local_entity_id="e1",
        mention_quote=quote,
        mention_kind="descriptor",
        representative_name=quote,
    )


def _fact(
    *,
    local_id: str = "f1",
    quote: str = "男子身材挺拔",
    proposition: str = "男子身材挺拔。",
) -> LocalObservationFact:
    return LocalObservationFact(
        local_fact_id=local_id,
        entity_ref="e1",
        evidence_quote=quote,
        raw_proposition=proposition,
        coarse_family="body",
        epistemic_status="asserted",
    )


def _request(
    text: str,
    *,
    entities: list[LocalObservationEntity] | None = None,
    facts: list[LocalObservationFact] | None = None,
    signals: list[LocalObservationTemporalSignal] | None = None,
    unresolved: list[LocalObservationUnresolvedItem] | None = None,
    max_context_chars: int = 600,
) -> LocalGroundingExecutionRequest:
    return LocalGroundingExecutionRequest(
        schema_version="local-grounding-input-v1",
        run_id="run-1",
        source_document_version_id="source-v1",
        chunk_id="chunk-1",
        chunk_text=text,
        discovery=LocalObservationDiscoveryResult(
            schema_version="local-observation-discovery-v1.1",
            chunk_id="chunk-1",
            entities=entities if entities is not None else [_entity()],
            facts=facts if facts is not None else [],
            temporal_signals=signals if signals is not None else [],
            unresolved_items=unresolved if unresolved is not None else [],
        ),
        max_context_chars=max_context_chars,
    )


def test_n2_grounds_unique_fact_and_builds_minimal_sentence_context() -> None:
    text = "众人停下脚步。男子年龄在二十左右，英俊的相貌，配上挺拔的身材。大厅里十分安静。"
    quote = "男子年龄在二十左右，英俊的相貌，配上挺拔的身材"
    request = _request(
        text,
        facts=[_fact(quote=quote, proposition="男子年龄二十左右、相貌英俊、身材挺拔。")],
    )

    first = LocalGroundingService().ground(request)
    second = LocalGroundingService().ground(request)

    assert first.status == "succeeded"
    assert first.counts.grounded_facts == 1
    grounded = first.output.grounded_facts[0]
    assert grounded.grounding_status == "exact"
    assert grounded.evidence_span.source_quote == quote
    assert grounded.local_context.text == f"{quote}。"
    assert (
        grounded.local_context.text[
            grounded.local_context.focus_start : grounded.local_context.focus_end
        ]
        == quote
    )
    assert first.input_fingerprint == second.input_fingerprint
    assert first.output_fingerprint == second.output_fingerprint
    assert grounded.fact_id == second.output.grounded_facts[0].fact_id


def test_n2_defers_repeated_fact_quote_without_guessing_an_occurrence() -> None:
    request = _request(
        "男子穿着白衣。男子后来又换上白衣。",
        facts=[_fact(quote="白衣", proposition="男子穿着白衣。")],
    )

    artifact = LocalGroundingService().ground(request)

    assert artifact.counts.grounded_facts == 0
    assert artifact.output.deferred_items[0].reason_code == "ambiguous_evidence"
    assert artifact.output.deferred_items[0].occurrence_count == 2


def test_n2_rejects_missing_or_model_repaired_quotes() -> None:
    missing = LocalGroundingService().ground(
        _request("男子有一头白发。", facts=[_fact(quote="黑发")])
    )
    repaired = LocalGroundingService().ground(
        _request(
            "男子衣袍胸口处赫然绘有一弯银色浅月。",
            facts=[_fact(quote="赫然绘有弯银色浅月")],
        )
    )

    assert missing.output.rejected_items[0].reason_code == "quote_not_in_chunk"
    assert repaired.output.rejected_items[0].reason_code == "unsupported_quote_repair"


def test_n2_accepts_unique_whitespace_normalization_and_preserves_source_span() -> None:
    artifact = LocalGroundingService().ground(
        _request(
            "男子披着旧\n青氅。",
            facts=[_fact(quote="旧青氅", proposition="男子披着旧青氅。")],
        )
    )

    grounded = artifact.output.grounded_facts[0]
    assert grounded.grounding_status == "normalized_unique"
    assert grounded.evidence_quote == "旧\n青氅"
    assert grounded.evidence_span.source_quote == "旧\n青氅"


def test_n2_deduplicates_facts_and_keeps_signal_bound_to_canonical_fact() -> None:
    facts = [_fact(local_id="f1"), _fact(local_id="f2")]
    signal = LocalObservationTemporalSignal(
        local_signal_id="t1",
        entity_ref="e1",
        fact_ref="f2",
        evidence_quote="男子身材挺拔",
        signal_kind="other_state",
        raw_label="男子身材挺拔",
    )

    artifact = LocalGroundingService().ground(
        _request("男子身材挺拔。", facts=facts, signals=[signal])
    )

    assert artifact.counts.grounded_facts == 1
    assert artifact.output.rejected_items[0].reason_code == "deterministic_duplicate"
    assert artifact.output.grounded_signals[0].grounded_fact_id == (
        artifact.output.grounded_facts[0].fact_id
    )


def test_n2_rejects_fact_unresolved_double_write_on_both_sides() -> None:
    fact = _fact()
    unresolved = LocalObservationUnresolvedItem(
        local_item_id="u1",
        entity_ref="e1",
        evidence_quote=fact.evidence_quote,
        raw_proposition=fact.raw_proposition,
        reason_code="ambiguous_local_scope",
    )

    artifact = LocalGroundingService().ground(
        _request("男子身材挺拔。", facts=[fact], unresolved=[unresolved])
    )

    assert artifact.counts.grounded_facts == 0
    assert [item.reason_code for item in artifact.output.rejected_items] == [
        "asserted_unresolved_double_write",
        "asserted_unresolved_double_write",
    ]


def test_n2_preserves_located_m1_unresolved_item_as_deferred() -> None:
    unresolved = LocalObservationUnresolvedItem(
        local_item_id="u1",
        entity_ref="e1",
        evidence_quote="男子身上的奇异光纹",
        raw_proposition="男子身上的奇异光纹无法确定局部范围。",
        reason_code="ambiguous_local_scope",
    )

    artifact = LocalGroundingService().ground(
        _request("男子身上的奇异光纹若隐若现。", unresolved=[unresolved])
    )

    item = artifact.output.deferred_items[0]
    assert item.source_kind == "unresolved_item"
    assert item.reason_code == "ambiguous_local_scope"
    assert item.upstream_reason_code == "ambiguous_local_scope"


def test_n2_defers_signal_when_its_bound_fact_is_not_grounded() -> None:
    signal = LocalObservationTemporalSignal(
        local_signal_id="t1",
        entity_ref="e1",
        fact_ref="f1",
        evidence_quote="白衣",
        signal_kind="presentation",
        raw_label="白衣",
    )
    artifact = LocalGroundingService().ground(
        _request(
            "男子穿上白衣，稍后又脱下白衣。",
            facts=[_fact(quote="白衣", proposition="男子穿上白衣。")],
            signals=[signal],
        )
    )

    reasons = [item.reason_code for item in artifact.output.deferred_items]
    assert reasons == ["ambiguous_evidence", "grounded_fact_unavailable"]
    assert artifact.output.grounded_signals == ()


def test_n2_does_not_block_field_grounding_on_ambiguous_mention_location() -> None:
    artifact = LocalGroundingService().ground(
        _request(
            "男子站在门边，另一名男子身材挺拔。",
            facts=[_fact(quote="另一名男子身材挺拔")],
        )
    )

    assert artifact.output.mention_nodes[0].grounding_status == "ambiguous"
    assert artifact.counts.grounded_facts == 1


def test_n2_bounds_long_sentence_context_without_cutting_the_focus_quote() -> None:
    prefix = "甲" * 90
    suffix = "乙" * 90
    quote = "男子身材挺拔"
    artifact = LocalGroundingService().ground(
        _request(
            f"{prefix}{quote}{suffix}。",
            facts=[_fact(quote=quote)],
            max_context_chars=64,
        )
    )

    context = artifact.output.grounded_facts[0].local_context
    assert len(context.text) == 64
    assert context.text[context.focus_start : context.focus_end] == quote


def test_n2_defers_fact_when_evidence_itself_exceeds_context_budget() -> None:
    quote = "高" * 65
    artifact = LocalGroundingService().ground(
        _request(
            f"男子{quote}。",
            facts=[_fact(quote=quote, proposition="男子很高。")],
            max_context_chars=64,
        )
    )

    assert artifact.output.deferred_items[0].reason_code == "local_context_budget_exceeded"
