from __future__ import annotations

from uuid import UUID

import pytest

from novel_character_generator.infrastructure.providers.mock import MockExtractionProvider


@pytest.mark.asyncio
async def test_mock_extraction_is_deterministic() -> None:
    provider = MockExtractionProvider()
    text = "第一章\n角色：林昭|黑发，佩剑\n角色：苏晚|白衣"

    first = await provider.extract(text)
    second = await provider.extract(text)

    assert [item.name for item in first] == ["林昭", "苏晚"]
    assert first[0].id == second[0].id
    assert first[0].novel_id == UUID(int=0)
