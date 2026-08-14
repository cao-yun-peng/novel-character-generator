from __future__ import annotations

from typing import Protocol

from novel_character_generator.domain.models import Character


class ExtractionProvider(Protocol):
    async def extract(self, text: str) -> list[Character]: ...


class ImageResult:
    def __init__(self, request_id: str, content: bytes) -> None:
        self.request_id = request_id
        self.content = content


class ImageProvider(Protocol):
    async def submit(self, character: Character, idempotency_key: str) -> str: ...

    async def fetch_result(self, request_id: str) -> ImageResult: ...
