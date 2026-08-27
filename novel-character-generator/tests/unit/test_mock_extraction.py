import pytest

from novel_character_generator.application.services.visual_candidate_adapter import (
    adapt_visual_candidates,
)
from novel_character_generator.domain.policies.grounding import (
    observation_fingerprint,
    validate_evidence,
)
from novel_character_generator.infrastructure.llm.mock import MockExtractionProvider


@pytest.mark.asyncio
async def test_mock_extraction_returns_grounded_character_data() -> None:
    text = "少年沈砚披着旧青氅。他左眼下有一颗浅痣，茶摊老板称他为“阿砚”。沈砚嘴角微扬。"
    candidates = await MockExtractionProvider().extract_chunk(text)
    result = adapt_visual_candidates(text, candidates)
    assert any(mention.text == "沈砚" for mention in result.mentions)
    assert any(item.field_path == "face.distinctive_mark" for item in result.observations)
    for item in result.observations:
        assert validate_evidence(text, item.evidence_quote, item.start, item.end) == "exact"


def test_grounding_and_fingerprint_are_deterministic() -> None:
    assert validate_evidence("沈砚黑发", "黑发", 2, 4) == "exact"
    assert validate_evidence("沈砚黑发", "白发", 2, 4) == "ungrounded"
    arguments = {
        "source_version": "v1",
        "start": 2,
        "end": 4,
        "field_path": "hair.color",
        "value": "黑发",
        "extractor_version": "mock-v1",
    }
    assert observation_fingerprint(**arguments) == observation_fingerprint(**arguments)
