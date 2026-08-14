import hashlib
import re
import unicodedata
from collections.abc import Iterable

from novel_character_generator.domain.entities.document import (
    ChapterBoundary,
    NormalizedText,
    TextChunk,
)

NORMALIZATION_MAP_VERSION = "unicode-nfc-newline-invisible-v1"
CHAPTER_HEADING = re.compile(
    r"(?m)^(?:第[〇零一二三四五六七八九十百千万两0-9]+[卷章节回部篇]"
    r"|卷[〇零一二三四五六七八九十百千万两0-9]+)[^\n]{0,80}$"
)
INVISIBLE_CHARACTERS = {"\ufeff", "\u200b", "\u200c", "\u200d", "\u2060"}
SENTENCE_END = re.compile(r"(?<=[。！？!?；;])")


def decode_text(data: bytes) -> tuple[str, str]:
    if not data:
        raise ValueError("empty_text_file")
    # Only attempt UTF-16 when a BOM makes the byte order unambiguous. Without
    # this guard, many ordinary GB18030 byte sequences decode as plausible but
    # corrupt UTF-16 text.
    encodings = ["utf-8-sig", "gb18030"]
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        encodings.insert(0, "utf-16")
    for encoding in encodings:
        try:
            text = data.decode(encoding)
        except UnicodeError:
            continue
        if "\x00" in text:
            continue
        return text, encoding
    raise ValueError("unsupported_text_encoding")


def normalize_text(original: str) -> NormalizedText:
    output: list[str] = []
    boundaries = [0]
    index = 0
    while index < len(original):
        start = index
        if original[index : index + 2] == "\r\n":
            segment = "\n"
            index += 2
        elif original[index] == "\r":
            segment = "\n"
            index += 1
        else:
            index += 1
            while index < len(original) and unicodedata.combining(original[index]):
                index += 1
            raw_segment = original[start:index]
            segment = (
                ""
                if raw_segment in INVISIBLE_CHARACTERS
                else unicodedata.normalize("NFC", raw_segment)
            )
        if not segment:
            boundaries[-1] = index
            continue
        output.extend(segment)
        for offset in range(len(segment)):
            boundaries.append(index if offset == len(segment) - 1 else start)
    return NormalizedText(
        text="".join(output),
        original_boundaries=boundaries,
        map_version=NORMALIZATION_MAP_VERSION,
    )


def detect_chapters(text: str) -> list[ChapterBoundary]:
    matches = list(CHAPTER_HEADING.finditer(text))
    if not matches:
        return [
            ChapterBoundary(
                ordinal=0,
                title=None,
                normalized_start=0,
                normalized_end=len(text),
            )
        ]
    chapters: list[ChapterBoundary] = []
    if matches[0].start() > 0 and text[: matches[0].start()].strip():
        chapters.append(
            ChapterBoundary(
                ordinal=0,
                title=None,
                normalized_start=0,
                normalized_end=matches[0].start(),
            )
        )
    for match_index, match in enumerate(matches):
        end = matches[match_index + 1].start() if match_index + 1 < len(matches) else len(text)
        chapters.append(
            ChapterBoundary(
                ordinal=len(chapters),
                title=match.group(0).strip(),
                normalized_start=match.start(),
                normalized_end=end,
            )
        )
    return chapters


def estimate_tokens(text: str) -> int:
    ascii_count = sum(character.isascii() for character in text)
    return max(1, len(text) - ascii_count + (ascii_count + 3) // 4)


def _paragraph_ranges(text: str, start: int, end: int) -> Iterable[tuple[int, int]]:
    cursor = start
    for match in re.finditer(r"\n\s*\n+", text[start:end]):
        boundary = start + match.end()
        if text[cursor:boundary].strip():
            yield cursor, boundary
        cursor = boundary
    if text[cursor:end].strip():
        yield cursor, end


def _split_range(text: str, start: int, end: int, target_tokens: int) -> list[tuple[int, int]]:
    if estimate_tokens(text[start:end]) <= target_tokens:
        return [(start, end)]
    ranges: list[tuple[int, int]] = []
    cursor = start
    for sentence in SENTENCE_END.split(text[start:end]):
        sentence_end = cursor + len(sentence)
        if sentence and estimate_tokens(sentence) > target_tokens:
            unit = max(1, target_tokens)
            while cursor < sentence_end:
                ranges.append((cursor, min(sentence_end, cursor + unit)))
                cursor = ranges[-1][1]
        elif sentence:
            ranges.append((cursor, sentence_end))
            cursor = sentence_end
    return ranges


def build_chunks(
    normalized: NormalizedText,
    chapters: list[ChapterBoundary],
    *,
    target_tokens: int,
    overlap_tokens: int = 0,
) -> list[TextChunk]:
    if not 1_000 <= target_tokens <= 12_000:
        raise ValueError("target_tokens_outside_poc_range")
    if overlap_tokens < 0 or overlap_tokens >= target_tokens:
        raise ValueError("invalid_overlap_tokens")
    chunks: list[TextChunk] = []
    for chapter in chapters:
        units: list[tuple[int, int]] = []
        for start, end in _paragraph_ranges(
            normalized.text, chapter.normalized_start, chapter.normalized_end
        ):
            units.extend(_split_range(normalized.text, start, end, target_tokens))
        cursor = 0
        while cursor < len(units):
            group_start = cursor
            start = units[cursor][0]
            end = units[cursor][1]
            cursor += 1
            while cursor < len(units):
                candidate_end = units[cursor][1]
                if estimate_tokens(normalized.text[start:candidate_end]) > target_tokens:
                    break
                end = candidate_end
                cursor += 1
            original_start, original_end = normalized.original_span(start, end)
            content = normalized.text[start:end]
            chunks.append(
                TextChunk(
                    ordinal=len(chunks),
                    chapter_ordinal=chapter.ordinal,
                    content=content,
                    content_hash=hashlib.sha256(content.encode()).hexdigest(),
                    normalized_start=start,
                    normalized_end=end,
                    original_start=original_start,
                    original_end=original_end,
                )
            )
            if overlap_tokens and cursor < len(units):
                overlap_start = cursor
                while overlap_start > group_start + 1:
                    candidate = units[overlap_start - 1][0]
                    if estimate_tokens(normalized.text[candidate:end]) > overlap_tokens:
                        break
                    overlap_start -= 1
                cursor = min(cursor, max(group_start + 1, overlap_start))
    return chunks
