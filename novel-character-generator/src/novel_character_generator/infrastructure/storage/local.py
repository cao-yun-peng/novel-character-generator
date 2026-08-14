import asyncio
from pathlib import Path
from urllib.parse import unquote, urlparse


class LocalArtifactStore:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    async def put(self, *, content_hash: str, data: bytes) -> str:
        if len(content_hash) != 64 or not content_hash.isalnum():
            raise ValueError("invalid_content_hash")
        path = self.root / content_hash[:2] / content_hash[2:4] / content_hash
        await asyncio.to_thread(path.parent.mkdir, parents=True, exist_ok=True)
        exists = await asyncio.to_thread(path.exists)
        if not exists:
            await asyncio.to_thread(path.write_bytes, data)
        return path.as_uri()

    async def get(self, storage_uri: str) -> bytes:
        parsed = urlparse(storage_uri)
        if parsed.scheme != "file":
            raise ValueError("unsupported_artifact_uri")
        path = await asyncio.to_thread(Path(unquote(parsed.path)).resolve)
        if not path.is_relative_to(self.root):
            raise ValueError("artifact_path_outside_root")
        return await asyncio.to_thread(path.read_bytes)
