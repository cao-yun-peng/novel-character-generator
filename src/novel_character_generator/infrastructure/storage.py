from __future__ import annotations

from pathlib import Path


class LocalArtifactStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    async def put(self, key: str, content: bytes) -> str:
        path = self.root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path.as_uri()
