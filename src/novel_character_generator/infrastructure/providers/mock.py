from __future__ import annotations

import hashlib
from uuid import UUID, uuid5

from novel_character_generator.application.ports import ImageResult
from novel_character_generator.domain.models import Character

MOCK_NAMESPACE = UUID("bf48e840-5cf8-4e65-8a53-8b024c21d5f0")


class MockExtractionProvider:
    async def extract(self, text: str) -> list[Character]:
        results: list[Character] = []
        for line in text.splitlines():
            if not line.startswith("角色："):
                continue
            parts = line.removeprefix("角色：").split("|", maxsplit=1)
            name = parts[0].strip()
            description = parts[1].strip() if len(parts) == 2 else None
            results.append(
                Character(
                    id=uuid5(MOCK_NAMESPACE, name),
                    novel_id=UUID(int=0),
                    name=name,
                    description=description,
                )
            )
        return results


class MockImageProvider:
    def __init__(self) -> None:
        self.submissions: dict[str, bytes] = {}

    async def submit(self, character: Character, idempotency_key: str) -> str:
        request_id = hashlib.sha256(idempotency_key.encode()).hexdigest()[:24]
        self.submissions.setdefault(
            request_id,
            f"MOCK_IMAGE\n{character.name}\n{character.description or ''}".encode(),
        )
        return request_id

    async def fetch_result(self, request_id: str) -> ImageResult:
        return ImageResult(request_id=request_id, content=self.submissions[request_id])
