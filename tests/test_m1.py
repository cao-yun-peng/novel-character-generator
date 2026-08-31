import unittest

from novel_character_generator.chunking import build_document_chunk_manifest
from novel_character_generator.errors import ContractValidationError
from novel_character_generator.grounding import ground_m1_result
from novel_character_generator.m1 import (
    M1ModelOutput,
    M1OrchestrationEnvelope,
    M1Orchestrator,
    M1ProviderRequest,
    M1_SYSTEM_INSTRUCTION,
)


class RecordingProvider:
    def __init__(self, response: object) -> None:
        self.response = response
        self.requests: list[M1ProviderRequest] = []

    def generate(self, request: M1ProviderRequest) -> object:
        self.requests.append(request)
        return self.response


def envelope_for(text: str) -> M1OrchestrationEnvelope:
    manifest = build_document_chunk_manifest(
        text,
        source_document_version_id="novel-v1",
        chunk_size=max(1, len(text)),
        overlap_characters=0,
        chunking_policy_version="test-chunking-v1",
    )
    return M1OrchestrationEnvelope.from_manifest_entry(
        source_document_version_id=manifest.source_document_version_id,
        chunking_policy_version=manifest.chunking_policy_version,
        entry=manifest.chunks[0],
        document_text=text,
    )


class M1BoundaryTests(unittest.TestCase):
    def test_prompt_keeps_the_frozen_minimal_mention_rule(self) -> None:
        self.assertIn("林黛玉", M1_SYSTEM_INSTRUCTION)
        self.assertIn("拆出 exact", M1_SYSTEM_INSTRUCTION)
        self.assertIn("describe", M1_SYSTEM_INSTRUCTION)
        self.assertIn("不做外貌字段分类", M1_SYSTEM_INSTRUCTION)

    def test_provider_only_receives_minimal_model_payload(self) -> None:
        text = "青衫老者身形高瘦，留着花白胡须。"
        provider = RecordingProvider(
            {
                "candidate_mentions": [
                    {
                        "mention_type": "describe",
                        "mention_scope": "individual",
                        "mention_quote": "青衫老者",
                        "evidence_quotes": ["青衫老者身形高瘦，留着花白胡须"],
                    }
                ]
            }
        )
        result = M1Orchestrator(provider).run(envelope_for(text))

        self.assertEqual(provider.requests[0].user_payload, {"chunk_text": text})
        self.assertNotIn("chunk_id", provider.requests[0].user_payload)
        self.assertNotIn("chunk_hash", provider.requests[0].user_payload)
        self.assertTrue(provider.requests[0].response_schema["additionalProperties"] is False)
        self.assertEqual(result.mentions[0].local_mention_id, "m1")

    def test_model_output_rejects_system_fields(self) -> None:
        with self.assertRaisesRegex(ContractValidationError, "extra=.*chunk_id"):
            M1ModelOutput.parse({"candidate_mentions": [], "chunk_id": "hostile-model-id"})

    def test_null_type_requires_null_quote(self) -> None:
        with self.assertRaisesRegex(ContractValidationError, "requires null"):
            M1ModelOutput.parse(
                {
                    "candidate_mentions": [
                        {
                            "mention_type": None,
                            "mention_scope": None,
                            "mention_quote": "null",
                            "evidence_quotes": ["只见一双手苍白瘦削"],
                        }
                    ]
                }
            )

    def test_exact_type_requires_non_empty_quote(self) -> None:
        with self.assertRaises(ContractValidationError):
            M1ModelOutput.parse(
                {
                    "candidate_mentions": [
                        {
                            "mention_type": "exact",
                            "mention_scope": "individual",
                            "mention_quote": "",
                            "evidence_quotes": ["原文"],
                        }
                    ]
                }
            )

    def test_duplicate_evidence_is_rejected_by_model_schema_gate(self) -> None:
        with self.assertRaisesRegex(ContractValidationError, "unique"):
            M1ModelOutput.parse(
                {
                    "candidate_mentions": [
                        {
                            "mention_type": "exact",
                            "mention_scope": "individual",
                            "mention_quote": "林黛玉",
                            "evidence_quotes": ["林黛玉眉目清秀", "林黛玉眉目清秀"],
                        }
                    ]
                }
            )

    def test_invalid_json_is_rejected(self) -> None:
        provider = RecordingProvider("not-json")
        with self.assertRaisesRegex(ContractValidationError, "invalid JSON"):
            M1Orchestrator(provider).run(envelope_for("林黛玉眉目清秀"))


class GroundingTests(unittest.TestCase):
    def test_exact_evidence_precedence_removes_fully_shadowed_describe(self) -> None:
        evidence_quotes = [
            "微笑的小脸",
            "小脸上露出可爱的小酒窝",
            "纤细的指尖",
            "修长的睫毛",
            "光洁侧脸",
            "小嘴泛起了柔和的笑意",
            "美丽的眼睛微弯",
            "小小年纪",
        ]
        text = "萧熏儿和少女。" + "。".join(evidence_quotes) + "。"
        response = {
            "candidate_mentions": [
                {
                    "mention_type": "exact",
                    "mention_scope": "individual",
                    "mention_quote": "萧熏儿",
                    "evidence_quotes": evidence_quotes,
                },
                {
                    "mention_type": "describe",
                    "mention_scope": "individual",
                    "mention_quote": "少女",
                    "evidence_quotes": evidence_quotes,
                },
            ]
        }
        bound = M1Orchestrator(RecordingProvider(response)).run(envelope_for(text))
        grounded = ground_m1_result(bound)

        self.assertEqual([item.mention_quote for item in grounded.grounded_mentions], ["萧熏儿"])
        self.assertEqual(
            bound.model_output.candidate_mentions[1].evidence_quotes,
            tuple(evidence_quotes),
        )
        self.assertEqual(
            [event.code for event in grounded.trace_events].count(
                "describe_evidence_shadowed_by_exact"
            ),
            len(evidence_quotes),
        )
        self.assertEqual(grounded.trace_events[-1].code, "describe_removed_after_exact_dedup")

    def test_exact_evidence_precedence_keeps_non_duplicate_describe_evidence(self) -> None:
        text = "萧熏儿与少女。微笑的小脸。少女身材修长。"
        response = {
            "candidate_mentions": [
                {
                    "mention_type": "exact",
                    "mention_scope": "individual",
                    "mention_quote": "萧熏儿",
                    "evidence_quotes": ["微笑的小脸"],
                },
                {
                    "mention_type": "describe",
                    "mention_scope": "individual",
                    "mention_quote": "少女",
                    "evidence_quotes": ["微笑的小脸", "少女身材修长"],
                },
            ]
        }
        first = ground_m1_result(M1Orchestrator(RecordingProvider(response)).run(envelope_for(text)))
        second = ground_m1_result(M1Orchestrator(RecordingProvider(response)).run(envelope_for(text)))

        describe = first.grounded_mentions[1]
        self.assertEqual(
            [item.evidence_quote for item in describe.approved_evidence],
            ["少女身材修长"],
        )
        self.assertEqual(describe.packet_hash, second.grounded_mentions[1].packet_hash)

    def test_exact_evidence_precedence_applies_to_collective_describe(self) -> None:
        text = "萧熏儿看向少年们，众人的脸色猛的一白。"
        response = {
            "candidate_mentions": [
                {
                    "mention_type": "exact",
                    "mention_scope": "individual",
                    "mention_quote": "萧熏儿",
                    "evidence_quotes": ["脸色猛的一白"],
                },
                {
                    "mention_type": "describe",
                    "mention_scope": "collective",
                    "mention_quote": "少年们",
                    "evidence_quotes": ["脸色猛的一白"],
                },
            ]
        }
        grounded = ground_m1_result(M1Orchestrator(RecordingProvider(response)).run(envelope_for(text)))
        self.assertEqual([item.mention_quote for item in grounded.grounded_mentions], ["萧熏儿"])
        self.assertEqual(grounded.quarantined_collective_mentions, ())

    def test_describe_evidence_is_unchanged_when_no_exact_owns_it(self) -> None:
        text = "少女有着微笑的小脸。"
        response = {
            "candidate_mentions": [
                {
                    "mention_type": "describe",
                    "mention_scope": "individual",
                    "mention_quote": "少女",
                    "evidence_quotes": ["微笑的小脸"],
                }
            ]
        }
        grounded = ground_m1_result(M1Orchestrator(RecordingProvider(response)).run(envelope_for(text)))
        self.assertEqual(
            [item.evidence_quote for item in grounded.grounded_mentions[0].approved_evidence],
            ["微笑的小脸"],
        )
        self.assertFalse(
            any(event.code == "describe_evidence_shadowed_by_exact" for event in grounded.trace_events)
        )

    def test_grounding_normalizes_suffix_and_keeps_valid_evidence(self) -> None:
        text = "红衣女子走近。她眉目清秀。红衣女子转身。"
        provider = RecordingProvider(
            {
                "candidate_mentions": [
                    {
                        "mention_type": "exact",
                        "mention_scope": "individual",
                        "mention_quote": "红衣女子",
                        "evidence_quotes": [
                            "红衣女子走近",
                            "她眉目清秀",
                            "模型虚构的证据",
                        ],
                    }
                ]
            }
        )
        bound = M1Orchestrator(provider).run(envelope_for(text))
        grounded = ground_m1_result(bound)

        mention = grounded.grounded_mentions[0]
        self.assertEqual(mention.local_mention_id, "m1")
        self.assertEqual(mention.mention_type, "describe")
        self.assertEqual(mention.mention_scope, "individual")
        self.assertNotIn("mention_occurrence_count", mention.to_dict())
        self.assertNotIn("mention_source_spans", mention.to_dict())
        self.assertEqual(
            [item.relation_to_mention for item in mention.approved_evidence],
            ["contains_mention", "contextual"],
        )
        self.assertEqual(grounded.rejected_evidence[0].reason_code, "evidence_not_in_chunk")
        self.assertEqual(grounded.trace_events[0].code, "mention_type_normalized_by_suffix")
        self.assertNotIn("trace_events", grounded.to_packet_dict())

    def test_null_mention_is_grounded_as_no_mention(self) -> None:
        text = "只见一双手苍白瘦削。"
        provider = RecordingProvider(
            {
                "candidate_mentions": [
                    {
                        "mention_type": None,
                        "mention_scope": None,
                        "mention_quote": None,
                        "evidence_quotes": ["一双手苍白瘦削"],
                    }
                ]
            }
        )
        grounded = ground_m1_result(M1Orchestrator(provider).run(envelope_for(text)))
        mention = grounded.grounded_mentions[0]
        self.assertIsNone(mention.mention_scope)
        self.assertNotIn("mention_quote_hash", mention.to_dict())
        self.assertNotIn("quote_hash", mention.approved_evidence[0].to_dict())
        self.assertEqual(mention.approved_evidence[0].relation_to_mention, "no_mention")

    def test_invalid_mention_rejects_its_block(self) -> None:
        provider = RecordingProvider(
            {
                "candidate_mentions": [
                    {
                        "mention_type": "exact",
                        "mention_scope": "individual",
                        "mention_quote": "不存在的人",
                        "evidence_quotes": ["她眉目清秀"],
                    }
                ]
            }
        )
        grounded = ground_m1_result(
            M1Orchestrator(provider).run(envelope_for("她眉目清秀。"))
        )
        self.assertEqual(grounded.grounded_mentions, ())
        self.assertEqual(grounded.rejected_evidence[0].reason_code, "mention_not_in_chunk")

    def test_packet_hash_is_deterministic(self) -> None:
        text = "林黛玉眉目清秀。"
        response = {
            "candidate_mentions": [
                {
                    "mention_type": "exact",
                    "mention_scope": "individual",
                    "mention_quote": "林黛玉",
                    "evidence_quotes": ["林黛玉眉目清秀"],
                }
            ]
        }
        first = ground_m1_result(M1Orchestrator(RecordingProvider(response)).run(envelope_for(text)))
        second = ground_m1_result(M1Orchestrator(RecordingProvider(response)).run(envelope_for(text)))
        self.assertEqual(
            first.grounded_mentions[0].packet_hash,
            second.grounded_mentions[0].packet_hash,
        )

    def test_whitespace_only_evidence_difference_recovers_raw_source_quote(self) -> None:
        text = "门房看去，只见十七道白色的身影。\n　　他们衣袂飘飘。"
        response = {
            "candidate_mentions": [
                {
                    "mention_type": "describe",
                    "mention_scope": "collective",
                    "mention_quote": "十七道白色的身影",
                    "evidence_quotes": ["十七道白色的身影。他们衣袂飘飘"],
                }
            ]
        }
        grounded = ground_m1_result(M1Orchestrator(RecordingProvider(response)).run(envelope_for(text)))

        evidence = grounded.grounded_mentions[0].approved_evidence[0]
        self.assertEqual(evidence.evidence_quote, "十七道白色的身影。\n　　他们衣袂飘飘")
        self.assertEqual(evidence.match_mode, "whitespace_equivalent")
        self.assertEqual(evidence.source_spans[0].quote(text), evidence.evidence_quote)

    def test_non_whitespace_evidence_rewrite_is_rejected(self) -> None:
        text = "门房眼睛湿润了。"
        response = {
            "candidate_mentions": [
                {
                    "mention_type": "describe",
                    "mention_scope": "individual",
                    "mention_quote": "门房",
                    "evidence_quotes": ["门房的眼睛湿润了"],
                }
            ]
        }
        grounded = ground_m1_result(M1Orchestrator(RecordingProvider(response)).run(envelope_for(text)))
        self.assertEqual(grounded.grounded_mentions, ())
        self.assertEqual(grounded.rejected_evidence[0].reason_code, "evidence_not_in_chunk")

    def test_collective_scope_is_quarantined_from_single_character_candidates(self) -> None:
        text = "门房衣衫破旧。十七道白色的身影衣袂飘飘。"
        response = {
            "candidate_mentions": [
                {
                    "mention_type": "describe",
                    "mention_scope": "individual",
                    "mention_quote": "门房",
                    "evidence_quotes": ["门房衣衫破旧"],
                },
                {
                    "mention_type": "describe",
                    "mention_scope": "collective",
                    "mention_quote": "十七道白色的身影",
                    "evidence_quotes": ["十七道白色的身影衣袂飘飘"],
                },
            ]
        }
        grounded = ground_m1_result(M1Orchestrator(RecordingProvider(response)).run(envelope_for(text)))
        self.assertEqual([item.mention_quote for item in grounded.single_character_mentions], ["门房"])
        self.assertEqual(
            [item.mention_quote for item in grounded.quarantined_collective_mentions],
            ["十七道白色的身影"],
        )

    def test_invalid_scope_combinations_fail_closed(self) -> None:
        invalid_candidates = [
            {
                "mention_type": "exact",
                "mention_scope": "collective",
                "mention_quote": "林黛玉",
                "evidence_quotes": ["林黛玉眉目清秀"],
            },
            {
                "mention_type": None,
                "mention_scope": "individual",
                "mention_quote": None,
                "evidence_quotes": ["一双手苍白瘦削"],
            },
        ]
        for candidate in invalid_candidates:
            with self.subTest(candidate=candidate):
                with self.assertRaises(ContractValidationError):
                    M1ModelOutput.parse({"candidate_mentions": [candidate]})


if __name__ == "__main__":
    unittest.main()
