from uuid import uuid4

from novel_character_generator.domain.entities.retrieval import RankedPassage
from novel_character_generator.domain.policies.retrieval import (
    ChineseSearchTermBuilder,
    build_retrieval_passages,
    reciprocal_rank_fusion,
)
from novel_character_generator.domain.policies.text_processing import (
    detect_chapters,
    normalize_text,
)


def test_retrieval_passages_keep_safe_boundaries_overlap_and_stable_ids() -> None:
    text = "第一章 初见\n" + "萧炎身着白衣。乌黑的长发垂在肩后。" * 12
    normalized = normalize_text(text)
    chapters = detect_chapters(normalized.text)
    build_id = uuid4()

    passages = build_retrieval_passages(
        normalized,
        chapters,
        build_id=build_id,
        target_tokens=64,
        overlap_tokens=20,
    )
    repeated = build_retrieval_passages(
        normalized,
        chapters,
        build_id=build_id,
        target_tokens=64,
        overlap_tokens=20,
    )

    assert len(passages) > 1
    assert [passage.id for passage in passages] == [passage.id for passage in repeated]
    assert passages[0].previous_passage_id is None
    assert passages[0].next_passage_id == passages[1].id
    assert passages[1].previous_passage_id == passages[0].id
    assert passages[-1].next_passage_id is None
    assert all(passage.content.rstrip().endswith(("。", "初见")) for passage in passages)
    assert passages[0].normalized_end > passages[1].normalized_start


def test_retrieval_passages_do_not_split_oversized_sentence() -> None:
    sentence = "黑发如瀑" * 40 + "。"
    normalized = normalize_text(sentence)
    passages = build_retrieval_passages(
        normalized,
        detect_chapters(normalized.text),
        build_id=uuid4(),
        target_tokens=32,
        overlap_tokens=4,
    )

    assert len(passages) == 1
    assert passages[0].content == sentence
    assert passages[0].oversized_sentence is True


def test_chinese_search_terms_preserve_two_character_names_and_visual_terms() -> None:
    builder = ChineseSearchTermBuilder(entity_terms=["萧炎", "云岚宗"])
    terms = builder.build("萧炎穿着白衣走入云岚宗。")

    assert "萧炎" in terms.body_terms.split()
    assert terms.entity_terms.split() == ["云岚宗", "萧炎"]
    assert "白衣" in terms.visual_terms.split()
    assert '"萧炎"' in builder.query("萧炎的白衣")


def test_rrf_keeps_both_channels_and_applies_entity_bonus() -> None:
    shared_id = uuid4()
    lexical_only_id = uuid4()
    entity_id = uuid4()

    fused = reciprocal_rank_fusion(
        [
            RankedPassage(passage_id=lexical_only_id, score=-2.0),
            RankedPassage(passage_id=shared_id, score=-1.0),
        ],
        [
            RankedPassage(passage_id=shared_id, score=0.9),
            RankedPassage(passage_id=entity_id, score=0.8),
        ],
        passage_contents={
            shared_id: "她穿着白衣。",
            lexical_only_id: "白衣落在地上。",
            entity_id: "萧炎站在门边。",
        },
        entity_terms=["萧炎"],
        rrf_k=60,
    )

    entity = next(hit for hit in fused if hit.passage_id == entity_id)
    lexical_only = next(hit for hit in fused if hit.passage_id == lexical_only_id)
    assert entity.exact_entity_match is True
    assert entity.rrf_score > lexical_only.rrf_score
    shared = next(hit for hit in fused if hit.passage_id == shared_id)
    assert shared.source_channels == ("bm25", "vector")
    assert shared.bm25_rank == 2
    assert shared.vector_rank == 1
