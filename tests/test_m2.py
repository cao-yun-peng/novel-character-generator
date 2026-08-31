import json
import unittest

from novel_character_generator.chunking import build_document_chunk_manifest
from novel_character_generator.errors import ContractValidationError
from novel_character_generator.grounding import ground_m1_result
from novel_character_generator.m1 import M1ModelOutput, M1OrchestrationEnvelope, M1Orchestrator
from novel_character_generator.m2 import (
    M2AttributionModelOutput,
    M2AttributionOrchestrator,
    M2OrchestrationEnvelope,
    M2PromotionEnvelope,
    M2PromotionModelOutput,
    M2PromotionOrchestrator,
    build_m2_attribution_envelopes,
    ground_m2_attribution_output,
    ground_m2_promotion_output,
)


class StaticProvider:
    def __init__(self, output):
        self.output = output
        self.requests = []

    def generate(self, request):
        self.requests.append(request)
        return self.output


def grounded(text, candidates):
    manifest = build_document_chunk_manifest(
        text,
        source_document_version_id="novel-v1",
        chunk_size=len(text),
        overlap_characters=0,
        chunking_policy_version="test-chunking-v1",
    )
    envelope = M1OrchestrationEnvelope.from_manifest_entry(
        source_document_version_id=manifest.source_document_version_id,
        chunking_policy_version=manifest.chunking_policy_version,
        entry=manifest.chunks[0],
        document_text=text,
    )
    provider = StaticProvider({"candidate_mentions": candidates})
    return ground_m1_result(M1Orchestrator(provider).run(envelope))


def fact(quote, category="face", attribute="眼睛", value="美丽"):
    return {
        "fact_quote": quote,
        "category": category,
        "attribute": attribute,
        "value": value,
    }


class M2EnvelopeTests(unittest.TestCase):
    def test_each_exact_receives_all_individual_describe_and_collective_is_quarantined(self):
        text = "萧熏儿睫毛修长。少女抬起美丽的眼睛。萧炎身形瘦削。众人身穿白衣。"
        result = grounded(
            text,
            [
                {"mention_type": "exact", "mention_scope": "individual", "mention_quote": "萧熏儿", "evidence_quotes": ["萧熏儿睫毛修长"]},
                {"mention_type": "describe", "mention_scope": "individual", "mention_quote": "少女", "evidence_quotes": ["少女抬起美丽的眼睛"]},
                {"mention_type": "exact", "mention_scope": "individual", "mention_quote": "萧炎", "evidence_quotes": ["萧炎身形瘦削"]},
                {"mention_type": "describe", "mention_scope": "collective", "mention_quote": "众人", "evidence_quotes": ["众人身穿白衣"]},
            ],
        )
        envelopes = build_m2_attribution_envelopes(result, chunk_text=text)
        self.assertEqual(len(envelopes), 2)
        for envelope in envelopes:
            payload = envelope.model_payload()
            self.assertEqual(len(payload["describe_blocks"]), 1)
            serialized = json.dumps(payload, ensure_ascii=False)
            self.assertNotIn("众人", json.dumps(payload["describe_blocks"], ensure_ascii=False))
            for forbidden in ("describe_ref", "fragment_ref", "span", "packet_hash", "task_cache_key"):
                self.assertNotIn(forbidden, serialized)

    def test_no_exact_yields_no_tasks_and_no_describe_still_yields_exact_task(self):
        describe_text = "少女有美丽的眼睛。"
        describe_result = grounded(
            describe_text,
            [{"mention_type": "describe", "mention_scope": "individual", "mention_quote": "少女", "evidence_quotes": ["少女有美丽的眼睛"]}],
        )
        self.assertEqual(build_m2_attribution_envelopes(describe_result, chunk_text=describe_text), ())

        exact_text = "萧熏儿有修长的睫毛。"
        exact_result = grounded(
            exact_text,
            [{"mention_type": "exact", "mention_scope": "individual", "mention_quote": "萧熏儿", "evidence_quotes": ["萧熏儿有修长的睫毛"]}],
        )
        envelope = build_m2_attribution_envelopes(exact_result, chunk_text=exact_text)[0]
        self.assertEqual(envelope.model_input.describe_blocks, ())

    def test_task_cache_key_is_stable_and_version_sensitive(self):
        text = "萧熏儿有修长的睫毛。少女有美丽的眼睛。"
        result = grounded(
            text,
            [
                {"mention_type": "exact", "mention_scope": "individual", "mention_quote": "萧熏儿", "evidence_quotes": ["萧熏儿有修长的睫毛"]},
                {"mention_type": "describe", "mention_scope": "individual", "mention_quote": "少女", "evidence_quotes": ["少女有美丽的眼睛"]},
            ],
        )
        first = M2OrchestrationEnvelope.from_grounding(result, chunk_text=text, target_local_mention_id="m1")
        replay = M2OrchestrationEnvelope.from_grounding(result, chunk_text=text, target_local_mention_id="m1")
        changed = M2OrchestrationEnvelope.from_grounding(
            result,
            chunk_text=text,
            target_local_mention_id="m1",
            resolver_version="changed-v2",
        )
        self.assertEqual(first.task_cache_key, replay.task_cache_key)
        self.assertNotEqual(first.task_cache_key, changed.task_cache_key)


class M2AttributionGroundingTests(unittest.TestCase):
    def make_envelope(self, text, candidates):
        result = grounded(text, candidates)
        return M2OrchestrationEnvelope.from_grounding(
            result, chunk_text=text, target_local_mention_id="m1"
        )

    def test_target_evidence_has_priority_and_earliest_occurrence_is_deterministic(self):
        text = "萧熏儿有修长的睫毛。少女也有修长的睫毛。"
        envelope = self.make_envelope(
            text,
            [
                {"mention_type": "exact", "mention_scope": "individual", "mention_quote": "萧熏儿", "evidence_quotes": ["萧熏儿有修长的睫毛"]},
                {"mention_type": "describe", "mention_scope": "individual", "mention_quote": "少女", "evidence_quotes": ["少女也有修长的睫毛"]},
            ],
        )
        output = M2AttributionModelOutput.parse({"belongs_to_target": [fact("修长的睫毛", attribute="睫毛", value="修长")]})
        result = ground_m2_attribution_output(envelope, output)
        self.assertEqual(result.grounded_belongs_to_target[0].source_mention_type, "exact")
        self.assertEqual(result.grounded_belongs_to_target[0].source_mention_id, "m1")

    def test_unique_describe_fact_is_hydrated_for_n3(self):
        text = "萧熏儿轻轻一笑。少女抬起美丽的眼睛。"
        envelope = self.make_envelope(
            text,
            [
                {"mention_type": "exact", "mention_scope": "individual", "mention_quote": "萧熏儿", "evidence_quotes": ["萧熏儿轻轻一笑"]},
                {"mention_type": "describe", "mention_scope": "individual", "mention_quote": "少女", "evidence_quotes": ["少女抬起美丽的眼睛"]},
            ],
        )
        result = ground_m2_attribution_output(
            envelope,
            M2AttributionModelOutput.parse({"belongs_to_target": [fact("美丽的眼睛")]}),
        )
        grounded_fact = result.grounded_belongs_to_target[0]
        self.assertEqual(grounded_fact.source_mention_id, "m2")
        self.assertEqual(grounded_fact.source_mention_type, "describe")
        self.assertEqual(grounded_fact.fact_chunk_span.quote(text), "美丽的眼睛")

    def test_ambiguous_describe_fact_fails_closed(self):
        text = "萧熏儿轻轻一笑。少女有美丽的眼睛。女子也有美丽的眼睛。"
        envelope = self.make_envelope(
            text,
            [
                {"mention_type": "exact", "mention_scope": "individual", "mention_quote": "萧熏儿", "evidence_quotes": ["萧熏儿轻轻一笑"]},
                {"mention_type": "describe", "mention_scope": "individual", "mention_quote": "少女", "evidence_quotes": ["少女有美丽的眼睛"]},
                {"mention_type": "describe", "mention_scope": "individual", "mention_quote": "女子", "evidence_quotes": ["女子也有美丽的眼睛"]},
            ],
        )
        result = ground_m2_attribution_output(
            envelope,
            M2AttributionModelOutput.parse({"belongs_to_target": [fact("美丽的眼睛")]}),
        )
        self.assertEqual(result.grounded_belongs_to_target, ())
        self.assertEqual(result.issues[0].code, "ambiguous_fact_binding")

    def test_whitespace_only_recovery_hydrates_raw_source_and_non_whitespace_edit_is_rejected(self):
        text = "萧熏儿轻轻一笑。少女抬起美丽的眼睛。"
        envelope = self.make_envelope(
            text,
            [
                {"mention_type": "exact", "mention_scope": "individual", "mention_quote": "萧熏儿", "evidence_quotes": ["萧熏儿轻轻一笑"]},
                {"mention_type": "describe", "mention_scope": "individual", "mention_quote": "少女", "evidence_quotes": ["少女抬起美丽的眼睛"]},
            ],
        )
        recovered = ground_m2_attribution_output(
            envelope,
            M2AttributionModelOutput.parse({"belongs_to_target": [fact("美丽 的眼睛")]}),
        )
        self.assertEqual(recovered.grounded_belongs_to_target[0].fact_quote, "美丽的眼睛")
        self.assertEqual(recovered.grounded_belongs_to_target[0].match_mode, "whitespace_equivalent")

        rejected = ground_m2_attribution_output(
            envelope,
            M2AttributionModelOutput.parse({"belongs_to_target": [fact("漂亮的眼睛")]}),
        )
        self.assertEqual(rejected.grounded_belongs_to_target, ())
        self.assertEqual(rejected.issues[0].code, "fact_not_in_allowed_evidence")

    def test_orchestrator_sends_only_minimal_payload_and_schema(self):
        text = "萧熏儿有修长的睫毛。少女有美丽的眼睛。"
        envelope = self.make_envelope(
            text,
            [
                {"mention_type": "exact", "mention_scope": "individual", "mention_quote": "萧熏儿", "evidence_quotes": ["萧熏儿有修长的睫毛"]},
                {"mention_type": "describe", "mention_scope": "individual", "mention_quote": "少女", "evidence_quotes": ["少女有美丽的眼睛"]},
            ],
        )
        provider = StaticProvider({"belongs_to_target": [fact("美丽的眼睛")]})
        result = M2AttributionOrchestrator(provider).run(envelope)
        request = provider.requests[0]
        self.assertEqual(request.response_schema_name, "m2_target_appearance_facts")
        self.assertEqual(set(request.user_payload), {"target", "describe_blocks", "chunk_text"})
        self.assertEqual(result.grounded_belongs_to_target[0].source_mention_type, "describe")

    def test_model_output_rejects_removed_fields(self):
        with self.assertRaises(ContractValidationError):
            M2AttributionModelOutput.parse(
                {"belongs_to_target": [{**fact("美丽的眼睛"), "support_span": {"start": 0, "end": 5}}]}
            )


class M2PromotionTests(unittest.TestCase):
    def make_envelope(self, text, evidence_quote=None, mention_quote="红衣女子"):
        evidence_quote = evidence_quote or text.rstrip("。")
        result = grounded(
            text,
            [{"mention_type": "describe", "mention_scope": "individual", "mention_quote": mention_quote, "evidence_quotes": [evidence_quote]}],
        )
        return M2PromotionEnvelope.from_grounded_describe(
            result, chunk_text=text, describe_local_mention_id="m1"
        )

    def test_promotes_one_character_and_preserves_unassigned_text(self):
        text = "红衣女子眉目清秀，身形纤细。"
        envelope = self.make_envelope(text)
        output = M2PromotionModelOutput.parse(
            {
                "characters": [
                    {
                        "character_label_quote": "红衣女子",
                        "belongs_to_character": [
                            fact("眉目清秀", attribute="眉目", value="清秀"),
                            fact("身形纤细", category="body", attribute="身形", value="纤细"),
                        ],
                    }
                ]
            }
        )
        result = ground_m2_promotion_output(envelope, output)
        self.assertEqual(len(result.promoted_characters), 1)
        self.assertEqual(result.promoted_characters[0].promoted_character_ref.promotion_index, 1)
        self.assertEqual(len(result.promoted_characters[0].grounded_belongs_to_character), 2)
        self.assertTrue(any("红衣女子" in item.fragment_quote for item in result.unassigned_fragments))

    def test_source_mention_label_is_allowed_without_a_label_span(self):
        text = "红衣女子眉目清秀。"
        envelope = self.make_envelope(text, evidence_quote="眉目清秀")
        output = M2PromotionModelOutput.parse(
            {"characters": [{"character_label_quote": "红衣女子", "belongs_to_character": [fact("眉目清秀", attribute="眉目", value="清秀")]}]}
        )
        result = ground_m2_promotion_output(envelope, output)
        packet = result.promoted_characters[0].to_dict()
        self.assertEqual(packet["character_label_quote"], "红衣女子")
        self.assertNotIn("character_label_span", packet)

    def test_multiple_characters_are_sorted_by_first_fact_not_model_order(self):
        text = "红衣女子眉目清秀，白衣少女身形纤细。"
        envelope = self.make_envelope(text)
        output = M2PromotionModelOutput.parse(
            {
                "characters": [
                    {"character_label_quote": "白衣少女", "belongs_to_character": [fact("身形纤细", category="body", attribute="身形", value="纤细")]},
                    {"character_label_quote": "红衣女子", "belongs_to_character": [fact("眉目清秀", attribute="眉目", value="清秀")]},
                ]
            }
        )
        result = ground_m2_promotion_output(envelope, output)
        self.assertEqual(
            [item.character_label_quote for item in result.promoted_characters],
            ["红衣女子", "白衣少女"],
        )
        self.assertEqual(
            [item.promoted_character_ref.promotion_index for item in result.promoted_characters],
            [1, 2],
        )

    def test_overlapping_characters_are_not_promoted(self):
        text = "红衣女子眉目清秀。"
        envelope = self.make_envelope(text)
        output = M2PromotionModelOutput.parse(
            {
                "characters": [
                    {"character_label_quote": "红衣女子", "belongs_to_character": [fact("眉目清秀", attribute="眉目", value="清秀")]},
                    {"character_label_quote": "女子", "belongs_to_character": [fact("目清秀", attribute="眉目", value="清秀")]},
                ]
            }
        )
        result = ground_m2_promotion_output(envelope, output)
        self.assertEqual(result.promoted_characters, ())
        self.assertTrue(result.promotion_review_required)
        self.assertIn("promotion_character_overlap", {item.code for item in result.issues})

    def test_ambiguous_fact_requires_review_and_preserves_entire_pool(self):
        text = "红衣女子眉目清秀，红衣女子仍眉目清秀。"
        envelope = self.make_envelope(text)
        output = M2PromotionModelOutput.parse(
            {"characters": [{"character_label_quote": "红衣女子", "belongs_to_character": [fact("眉目清秀", attribute="眉目", value="清秀")]}]}
        )
        result = ground_m2_promotion_output(envelope, output)
        self.assertEqual(result.promoted_characters, ())
        self.assertTrue(result.promotion_review_required)

    def test_ambiguous_fact_does_not_discard_unique_fact_for_same_character(self):
        text = "青衫老者身着青衫，露出浑浊的老眼。"
        envelope = self.make_envelope(text, mention_quote="青衫老者")
        output = M2PromotionModelOutput.parse(
            {
                "characters": [
                    {
                        "character_label_quote": "青衫老者",
                        "belongs_to_character": [
                            fact("青衫", category="clothing", attribute="衣着", value="青衫"),
                            fact("浑浊的老眼", attribute="眼睛", value="浑浊"),
                        ],
                    }
                ]
            }
        )
        result = ground_m2_promotion_output(envelope, output)

        self.assertEqual(len(result.promoted_characters), 1)
        accepted = result.promoted_characters[0].grounded_belongs_to_character
        self.assertEqual([item.fact_quote for item in accepted], ["浑浊的老眼"])
        self.assertEqual([item.code for item in result.issues], ["ambiguous_promotion_fact"])
        self.assertEqual(result.issues[0].fact_index, 0)
        self.assertEqual(result.issues[0].character_index, 0)
        self.assertEqual(result.issues[0].fact_quote, "青衫")
        self.assertEqual(result.issues[0].candidate_occurrence_count, 2)
        self.assertEqual(
            sum(fragment.fragment_quote.count("青衫") for fragment in result.unassigned_fragments),
            2,
        )
        self.assertFalse(any("浑浊的老眼" in item.fragment_quote for item in result.unassigned_fragments))

    def test_promotion_orchestrator_uses_minimal_boundary(self):
        text = "红衣女子眉目清秀。"
        envelope = self.make_envelope(text)
        provider = StaticProvider(
            {"characters": [{"character_label_quote": "红衣女子", "belongs_to_character": [fact("眉目清秀", attribute="眉目", value="清秀")]}]}
        )
        M2PromotionOrchestrator(provider).run(envelope)
        request = provider.requests[0]
        self.assertEqual(request.response_schema_name, "m2_promote_remaining_describe")
        self.assertEqual(set(request.user_payload), {"describe", "chunk_text"})
        serialized = json.dumps(request.user_payload, ensure_ascii=False)
        for forbidden in ("fragment_ref", "span", "packet_hash", "promotion_hash"):
            self.assertNotIn(forbidden, serialized)


if __name__ == "__main__":
    unittest.main()
