from novel_character_generator.domain.policies.grounding import locate_evidence_span


def test_locator_returns_unique_exact_source_span() -> None:
    text = "沈砚披着旧青氅。"

    location = locate_evidence_span(text, "旧青氅")

    assert location.status == "exact"
    assert (location.start, location.end) == (4, 7)
    assert location.source_quote == "旧青氅"


def test_locator_uses_entity_anchor_to_disambiguate_repeated_quote() -> None:
    text = "沈砚穿白衣。顾清遥也穿白衣。"

    location = locate_evidence_span(text, "白衣", anchor_quote="顾清遥")

    assert location.status == "exact"
    assert location.source_quote == "白衣"
    assert location.start == text.rfind("白衣")
    assert location.occurrence_count == 2


def test_locator_rejects_repeated_quote_when_anchor_does_not_resolve_it() -> None:
    text = "白衣立在沈砚左边，白衣立在沈砚右边。"

    location = locate_evidence_span(text, "白衣", anchor_quote="顾清遥")

    assert location.status == "ambiguous"
    assert location.start is None


def test_locator_maps_whitespace_normalized_quote_back_to_source() -> None:
    text = "沈砚披着旧\n青氅。"

    location = locate_evidence_span(text, "旧青氅")

    assert location.status == "normalized"
    assert location.source_quote == "旧\n青氅"
    assert text[location.start : location.end] == "旧\n青氅"


def test_locator_does_not_guess_missing_evidence() -> None:
    assert locate_evidence_span("沈砚黑发", "白发").status == "not_found"
