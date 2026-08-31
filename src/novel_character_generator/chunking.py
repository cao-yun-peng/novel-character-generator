from __future__ import annotations

from dataclasses import dataclass

from .errors import ContractValidationError
from .text import SourceSpan, sha256_text

DOCUMENT_CHUNK_MANIFEST_VERSION = "document-chunk-manifest-v3"
DEFAULT_CHUNKING_POLICY_VERSION = "fixed-codepoint-window-v1"


@dataclass(frozen=True)
class ChunkManifestEntry:
    chunk_id: str
    chunk_hash: str
    chunk_source_span: SourceSpan
    overlap_left_characters: int
    overlap_right_characters: int

    def to_dict(self) -> dict[str, object]:
        return {
            "chunk_id": self.chunk_id,
            "chunk_hash": self.chunk_hash,
            "chunk_source_span": self.chunk_source_span.to_dict(),
            "overlap_left_characters": self.overlap_left_characters,
            "overlap_right_characters": self.overlap_right_characters,
        }


@dataclass(frozen=True)
class DocumentChunkManifest:
    source_document_version_id: str
    document_hash: str
    chunking_policy_version: str
    total_characters: int
    coverage_status: str
    truncation_reason: str | None
    processed_source_end: int
    chunks: tuple[ChunkManifestEntry, ...]
    schema_version: str = DOCUMENT_CHUNK_MANIFEST_VERSION

    def validate(self, document_text: str) -> None:
        if self.schema_version != DOCUMENT_CHUNK_MANIFEST_VERSION:
            raise ContractValidationError("unsupported manifest schema_version")
        if not self.source_document_version_id or not self.chunking_policy_version:
            raise ContractValidationError("manifest identity fields must be non-empty")
        if not document_text:
            raise ContractValidationError("document_text must be non-empty")
        if self.total_characters != len(document_text):
            raise ContractValidationError("total_characters does not match document_text")
        if self.document_hash != sha256_text(document_text):
            raise ContractValidationError("document_hash does not match raw document text")
        if self.coverage_status not in {"complete", "truncated"}:
            raise ContractValidationError("coverage_status must be complete or truncated")
        if self.coverage_status == "complete":
            if self.truncation_reason is not None:
                raise ContractValidationError("complete coverage cannot have a truncation_reason")
            if self.processed_source_end != self.total_characters:
                raise ContractValidationError("complete coverage must reach the document end")
        else:
            if self.truncation_reason not in {
                "max_chunks",
                "max_characters",
                "provider_limit",
                "manual_stop",
                "source_read_error",
            }:
                raise ContractValidationError("truncated coverage needs a valid reason")
            if not 0 < self.processed_source_end < self.total_characters:
                raise ContractValidationError("truncated coverage must stop inside the document")
        if not self.chunks:
            raise ContractValidationError("manifest must contain at least one chunk")
        if self.chunks[0].chunk_source_span.start != 0:
            raise ContractValidationError("the first chunk must start at zero")
        if self.chunks[-1].chunk_source_span.end != self.processed_source_end:
            raise ContractValidationError("the last chunk must end at processed_source_end")

        for index, chunk in enumerate(self.chunks):
            span = chunk.chunk_source_span
            if span.end > self.total_characters:
                raise ContractValidationError("chunk span exceeds document bounds")
            raw_chunk = document_text[span.start : span.end]
            if chunk.chunk_hash != sha256_text(raw_chunk):
                raise ContractValidationError(f"chunk hash mismatch at index {index}")
            if chunk.overlap_left_characters < 0 or chunk.overlap_right_characters < 0:
                raise ContractValidationError("chunk overlaps cannot be negative")
            if index == 0:
                expected_left = 0
            else:
                previous = self.chunks[index - 1].chunk_source_span
                if span.start > previous.end:
                    raise ContractValidationError("adjacent chunks leave an undeclared gap")
                if span.start <= previous.start:
                    raise ContractValidationError("chunk starts must be strictly increasing")
                expected_left = previous.end - span.start
            if index == len(self.chunks) - 1:
                expected_right = 0
            else:
                following = self.chunks[index + 1].chunk_source_span
                expected_right = span.end - following.start
                if expected_right < 0:
                    raise ContractValidationError("adjacent chunks leave an undeclared gap")
            if chunk.overlap_left_characters != expected_left:
                raise ContractValidationError(f"left overlap mismatch at index {index}")
            if chunk.overlap_right_characters != expected_right:
                raise ContractValidationError(f"right overlap mismatch at index {index}")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "source_document_version_id": self.source_document_version_id,
            "document_hash": self.document_hash,
            "chunking_policy_version": self.chunking_policy_version,
            "total_characters": self.total_characters,
            "coverage_status": self.coverage_status,
            "truncation_reason": self.truncation_reason,
            "processed_source_end": self.processed_source_end,
            "chunks": [chunk.to_dict() for chunk in self.chunks],
        }


def build_document_chunk_manifest(
    document_text: str,
    *,
    source_document_version_id: str,
    chunk_size: int,
    overlap_characters: int,
    chunking_policy_version: str = DEFAULT_CHUNKING_POLICY_VERSION,
    max_chunks: int | None = None,
    max_characters: int | None = None,
) -> DocumentChunkManifest:
    """Build and validate a deterministic overlapping code-point manifest."""
    if not isinstance(document_text, str) or not document_text:
        raise ContractValidationError("document_text must be a non-empty string")
    if not source_document_version_id or not chunking_policy_version:
        raise ContractValidationError("version identifiers must be non-empty")
    if isinstance(chunk_size, bool) or not isinstance(chunk_size, int) or chunk_size < 1:
        raise ContractValidationError("chunk_size must be a positive integer")
    if (
        isinstance(overlap_characters, bool)
        or not isinstance(overlap_characters, int)
        or overlap_characters < 0
        or overlap_characters >= chunk_size
    ):
        raise ContractValidationError("overlap must satisfy 0 <= overlap < chunk_size")
    if max_chunks is not None and (
        isinstance(max_chunks, bool) or not isinstance(max_chunks, int) or max_chunks < 1
    ):
        raise ContractValidationError("max_chunks must be a positive integer")
    if max_characters is not None and (
        isinstance(max_characters, bool)
        or not isinstance(max_characters, int)
        or max_characters < 1
    ):
        raise ContractValidationError("max_characters must be a positive integer")

    total = len(document_text)
    character_limit = min(total, max_characters) if max_characters is not None else total
    raw_chunks: list[tuple[SourceSpan, str]] = []
    start = 0
    while start < character_limit and (max_chunks is None or len(raw_chunks) < max_chunks):
        end = min(start + chunk_size, character_limit)
        span = SourceSpan(start, end)
        raw_chunk = document_text[start:end]
        raw_chunks.append((span, sha256_text(raw_chunk)))
        if end == character_limit:
            break
        start = end - overlap_characters

    processed_end = raw_chunks[-1][0].end
    if processed_end == total:
        coverage_status = "complete"
        truncation_reason = None
    else:
        coverage_status = "truncated"
        truncation_reason = "max_chunks" if processed_end < character_limit else "max_characters"

    chunks: list[ChunkManifestEntry] = []
    for index, (span, chunk_hash) in enumerate(raw_chunks):
        left = 0 if index == 0 else raw_chunks[index - 1][0].end - span.start
        right = 0 if index == len(raw_chunks) - 1 else span.end - raw_chunks[index + 1][0].start
        chunk_id = f"chunk-{index + 1:06d}-{span.start}-{span.end}-{chunk_hash[:12]}"
        chunks.append(
            ChunkManifestEntry(
                chunk_id=chunk_id,
                chunk_hash=chunk_hash,
                chunk_source_span=span,
                overlap_left_characters=left,
                overlap_right_characters=right,
            )
        )

    manifest = DocumentChunkManifest(
        source_document_version_id=source_document_version_id,
        document_hash=sha256_text(document_text),
        chunking_policy_version=chunking_policy_version,
        total_characters=total,
        coverage_status=coverage_status,
        truncation_reason=truncation_reason,
        processed_source_end=processed_end,
        chunks=tuple(chunks),
    )
    manifest.validate(document_text)
    return manifest

