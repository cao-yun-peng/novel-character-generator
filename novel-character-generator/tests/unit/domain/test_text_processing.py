from novel_character_generator.domain.policies.text_processing import (
    build_chunks,
    decode_text,
    detect_chapters,
    normalize_text,
)


def test_normalization_preserves_reverse_offsets() -> None:
    original = "序\r\nA\u0301\u200b终"
    normalized = normalize_text(original)
    assert normalized.text == "序\nÁ终"
    assert normalized.original_span(1, 3) == (1, 6)
    assert original[slice(*normalized.original_span(3, 4))] == "终"


def test_decode_text_distinguishes_gb18030_from_utf16() -> None:
    for source in ("测试", "你好", "古风小说"):
        decoded, encoding = decode_text(source.encode("gb18030"))
        assert decoded == source
        assert encoding == "gb18030"

    utf16_source = "第一章 初见"
    decoded, encoding = decode_text(utf16_source.encode("utf-16"))
    assert decoded == utf16_source
    assert encoding == "utf-16"


def test_chapter_detection_and_chunk_hashes_are_stable() -> None:
    text = "序章说明\n\n第一章 初见\n" + "山河。" * 600 + "\n\n第二章 归来\n" + "星月。" * 400
    normalized = normalize_text(text)
    chapters = detect_chapters(normalized.text)
    first = build_chunks(normalized, chapters, target_tokens=1_000)
    second = build_chunks(normalized, chapters, target_tokens=1_000)
    assert [chapter.title for chapter in chapters] == [None, "第一章 初见", "第二章 归来"]
    assert len(first) >= 3
    assert [chunk.content_hash for chunk in first] == [chunk.content_hash for chunk in second]
    assert all(
        chunk.content == normalized.text[chunk.normalized_start : chunk.normalized_end]
        for chunk in first
    )
