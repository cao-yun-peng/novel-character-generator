import unittest

from novel_character_generator.grounding import ApprovedEvidence, GroundedMention, GroundingResult
from novel_character_generator.m2 import LocalCharacterRef, M2GroundedAttributionResult, M2GroundedFact
from novel_character_generator.n3 import resolve_n3_chunk
from novel_character_generator.text import SourceSpan, sha256_text


HASH = "a" * 64


def mention(local_id, mention_type, quote, evidence_quote, span, *, scope="individual"):
    return GroundedMention(
        local_mention_id=local_id,
        mention_type=mention_type,
        mention_scope=scope,
        mention_quote=quote,
        approved_evidence=(
            ApprovedEvidence(
                evidence_quote=evidence_quote,
                occurrence_count=1,
                source_spans=(span,),
                relation_to_mention="contextual",
                match_mode="exact",
            ),
        ),
        packet_hash=HASH,
    )


def grounded_result(chunk_id, target_id, *facts):
    return M2GroundedAttributionResult(
        target_character_ref=LocalCharacterRef("doc-v1", chunk_id, target_id, HASH),
        task_cache_key="b" * 64,
        grounded_belongs_to_target=tuple(facts),
        issues=(),
    )


def grounded_fact(text, *, source_id, source_type, evidence_span, fact_span, attribute, value):
    return M2GroundedFact(
        fact_quote=fact_span.quote(text),
        category="clothing",
        attribute=attribute,
        value=value,
        source_mention_id=source_id,
        source_mention_type=source_type,
        source_evidence_quote=evidence_span.quote(text),
        source_evidence_span=evidence_span,
        fact_chunk_span=fact_span,
        match_mode="exact",
    )


class N3Tests(unittest.TestCase):
    def make_grounding(self, text, *mentions):
        return GroundingResult(
            source_document_version_id="doc-v1",
            chunking_policy_version="test-v1",
            chunk_id="c0001",
            chunk_hash=sha256_text(text),
            chunk_source_span=SourceSpan(0, len(text)),
            grounded_mentions=tuple(mentions),
            rejected_evidence=(),
            trace_events=(),
        )

    def test_direct_exact_fact_is_kept_and_describe_remains_for_promotion(self):
        text = "甲黑发。少女红衣。"
        exact_span = SourceSpan(0, 3)
        describe_span = SourceSpan(4, len(text))
        grounding = self.make_grounding(
            text,
            mention("m1", "exact", "甲", exact_span.quote(text), exact_span),
            mention("m2", "describe", "少女", describe_span.quote(text), describe_span),
        )
        fact = grounded_fact(
            text,
            source_id="m1",
            source_type="exact",
            evidence_span=exact_span,
            fact_span=SourceSpan(1, 3),
            attribute="头发",
            value="黑",
        )
        result = resolve_n3_chunk(grounding, [grounded_result("c0001", "m1", fact)], chunk_text=text)
        self.assertEqual(len(result.target_appearance_packets[0].grounded_appearance_facts), 1)
        pool = result.describe_pool_results[0]
        self.assertEqual(pool.next_action, "promote_remaining_describe")
        self.assertEqual(pool.remaining_evidence_fragments[0].fragment_quote, "少女红衣。")

    def test_unique_describe_claim_is_consumed_and_assigned(self):
        text = "甲。少女红衣白鞋。"
        exact_span = SourceSpan(0, 1)
        describe_span = SourceSpan(2, len(text))
        grounding = self.make_grounding(
            text,
            mention("m1", "exact", "甲", "甲", exact_span),
            mention("m2", "describe", "少女", describe_span.quote(text), describe_span),
        )
        claim = grounded_fact(
            text,
            source_id="m2",
            source_type="describe",
            evidence_span=describe_span,
            fact_span=SourceSpan(4, 6),
            attribute="衣服",
            value="红",
        )
        result = resolve_n3_chunk(grounding, [grounded_result("c0001", "m1", claim)], chunk_text=text)
        self.assertEqual(result.target_appearance_packets[0].grounded_appearance_facts, (claim,))
        pool = result.describe_pool_results[0]
        self.assertEqual(len(pool.consumed_fragments), 1)
        self.assertFalse(any("红衣" in item.fragment_quote for item in pool.remaining_evidence_fragments))

    def test_cross_target_overlapping_claims_are_conflicted_and_not_promoted(self):
        text = "甲乙。少女红衣。"
        describe_span = SourceSpan(3, len(text))
        grounding = self.make_grounding(
            text,
            mention("m1", "exact", "甲", "甲", SourceSpan(0, 1)),
            mention("m2", "exact", "乙", "乙", SourceSpan(1, 2)),
            mention("m3", "describe", "少女", describe_span.quote(text), describe_span),
        )
        left = grounded_fact(text, source_id="m3", source_type="describe", evidence_span=describe_span, fact_span=SourceSpan(5, 7), attribute="衣服", value="红")
        right = grounded_fact(text, source_id="m3", source_type="describe", evidence_span=describe_span, fact_span=SourceSpan(5, 7), attribute="衣服", value="红")
        result = resolve_n3_chunk(
            grounding,
            [grounded_result("c0001", "m1", left), grounded_result("c0001", "m2", right)],
            chunk_text=text,
        )
        self.assertTrue(all(not item.grounded_appearance_facts for item in result.target_appearance_packets))
        pool = result.describe_pool_results[0]
        self.assertEqual(len(pool.conflicted_fragments), 2)
        self.assertFalse(any("红衣" in item.fragment_quote for item in pool.remaining_evidence_fragments))

    def test_nonoverlapping_claims_can_be_consumed_by_different_targets(self):
        text = "甲乙。少女红衣白鞋。"
        describe_span = SourceSpan(3, len(text))
        grounding = self.make_grounding(
            text,
            mention("m1", "exact", "甲", "甲", SourceSpan(0, 1)),
            mention("m2", "exact", "乙", "乙", SourceSpan(1, 2)),
            mention("m3", "describe", "少女", describe_span.quote(text), describe_span),
        )
        red = grounded_fact(text, source_id="m3", source_type="describe", evidence_span=describe_span, fact_span=SourceSpan(5, 7), attribute="衣服", value="红")
        shoes = grounded_fact(text, source_id="m3", source_type="describe", evidence_span=describe_span, fact_span=SourceSpan(7, 9), attribute="鞋", value="白")
        result = resolve_n3_chunk(
            grounding,
            [grounded_result("c0001", "m1", red), grounded_result("c0001", "m2", shoes)],
            chunk_text=text,
        )
        self.assertEqual([len(item.grounded_appearance_facts) for item in result.target_appearance_packets], [1, 1])
        self.assertEqual(len(result.describe_pool_results[0].consumed_fragments), 2)
        self.assertEqual(result.describe_pool_results[0].conflicted_fragments, ())

    def test_collective_is_quarantined_from_n3_pools(self):
        text = "甲。众人白衣。"
        grounding = self.make_grounding(
            text,
            mention("m1", "exact", "甲", "甲", SourceSpan(0, 1)),
            mention("m2", "describe", "众人", "众人白衣。", SourceSpan(2, len(text)), scope="collective"),
        )
        result = resolve_n3_chunk(grounding, [grounded_result("c0001", "m1")], chunk_text=text)
        self.assertEqual(result.describe_pool_results, ())


if __name__ == "__main__":
    unittest.main()
