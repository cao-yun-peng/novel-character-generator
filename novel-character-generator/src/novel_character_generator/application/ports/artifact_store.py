from typing import Protocol


class ArtifactStore(Protocol):
    async def put(self, *, content_hash: str, data: bytes) -> str: ...

    async def get(self, storage_uri: str) -> bytes: ...
