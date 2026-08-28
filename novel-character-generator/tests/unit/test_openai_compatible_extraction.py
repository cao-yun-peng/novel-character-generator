import asyncio
import json

import httpx
import pytest

from novel_character_generator.infrastructure.llm.openai_compatible import (
    EXTRACTION_PROMPT_VERSION,
    EXTRACTION_SYSTEM_PROMPT,
    EXTRACTION_SYSTEM_PROMPT_V2_5,
    EXTRACTION_SYSTEM_PROMPT_V2_6,
    OpenAICompatibleExtractionProvider,
    ProviderExtractionError,
    build_chunk_extraction_request,
    decode_provider_json,
    validate_provider_visual_candidate_payload,
)


def test_chunk_request_builder_matches_production_contract_without_credentials() -> None:
    body = build_chunk_extraction_request(
        "沈砚黑发",
        model="model-v1",
        system_prompt=EXTRACTION_SYSTEM_PROMPT_V2_6,
    )

    assert body["model"] == "model-v1"
    assert body["response_format"] == {"type": "json_object"}
    assert body["temperature"] == 0
    assert body["thinking"] == {"type": "disabled"}
    assert body["reasoning_effort"] == "none"
    assert body["max_tokens"] == 8_192
    assert "沈砚黑发" in body["messages"][1]["content"]
    assert "hair.color" in body["messages"][0]["content"]
    assert "distinctive_marks.beard" in body["messages"][0]["content"]
    assert "face.eyes" in body["messages"][0]["content"]
    assert "Never invent roots such as eyes.* or facial_hair.*" in body["messages"][0]["content"]
    assert "Appearance-based age estimates are inferred" in body["messages"][0]["content"]
    assert "damaged clothing, messy hair" in body["messages"][0]["content"]
    assert "MAP EACH FACT TO ITS SEMANTIC FIELD" in body["messages"][0]["content"]
    assert "unsupported_visual_field" in body["messages"][0]["content"]
    assert "face.eye_color is eye/iris color" in body["messages"][0]["content"]
    assert "belong to clothing.coverage" in body["messages"][0]["content"]
    assert "Never substitute one mark type for another" in body["messages"][0]["content"]
    assert "Split every explicit garment kind" in body["messages"][0]["content"]
    assert "shared modifier must be distributed" in body["messages"][0]["content"]
    assert "shortest continuous span" in body["messages"][0]["content"]
    assert "preserving explicit location" in body["messages"][0]["content"]
    assert "source-language semantic value" in body["messages"][0]["content"]
    assert "comma-separated attribute tuple" in body["messages"][0]["content"]
    assert "meta-statement" in body["messages"][0]["content"]
    assert "api_key" not in json.dumps(body)


def test_visual_prompt_rules_are_generic_and_do_not_embed_evaluation_examples() -> None:
    assert EXTRACTION_PROMPT_VERSION == "visual-extraction-prompt-v2.5"
    assert EXTRACTION_SYSTEM_PROMPT == EXTRACTION_SYSTEM_PROMPT_V2_5
    assert "explicit_name: only an explicit proper name" in EXTRACTION_SYSTEM_PROMPT_V2_6
    assert "is never explicit_name" in EXTRACTION_SYSTEM_PROMPT_V2_6
    assert "weapons, medicines, tools" in EXTRACTION_SYSTEM_PROMPT_V2_6
    assert "emit nested age.*" in EXTRACTION_SYSTEM_PROMPT_V2_6
    assert "physically visible overall face" in EXTRACTION_SYSTEM_PROMPT_V2_6
    assert "beauty, charm, desirability" in EXTRACTION_SYSTEM_PROMPT_V2_6
    assert "one candidate per independently renderable fact" in EXTRACTION_SYSTEM_PROMPT_V2_6
    assert "Multiple candidates may use the same field_path" in EXTRACTION_SYSTEM_PROMPT_V2_6
    assert "cultivation tiers" in EXTRACTION_SYSTEM_PROMPT_V2_6
    assert "powered forms, disguise activation" in EXTRACTION_SYSTEM_PROMPT_V2_6
    assert "novel-specific/non-visual field" in EXTRACTION_SYSTEM_PROMPT_V2_6
    assert "Do not attach it to unchanged age" in EXTRACTION_SYSTEM_PROMPT_V2_6
    assert "never implies identity across chunks" in EXTRACTION_SYSTEM_PROMPT_V2_6
    assert "unknown is not a container for ambiguous ownership" in EXTRACTION_SYSTEM_PROMPT_V2_6
    assert "inferred_visual_fact" in EXTRACTION_SYSTEM_PROMPT_V2_6
    assert "Do not duplicate that same signal at top level" in EXTRACTION_SYSTEM_PROMPT_V2_6
    assert "PHASE 7 — FINAL VALIDATION" in EXTRACTION_SYSTEM_PROMPT_V2_6
    assert "沈砚" not in EXTRACTION_SYSTEM_PROMPT_V2_6
    assert "顾川" not in EXTRACTION_SYSTEM_PROMPT_V2_6
    assert "梁策" not in EXTRACTION_SYSTEM_PROMPT_V2_6


def test_responses_request_uses_json_schema_and_total_output_budget() -> None:
    body = build_chunk_extraction_request(
        "沈砚黑发",
        model="model-v1",
        wire_api="responses",
        reasoning_effort="low",
        max_output_tokens=4_096,
    )

    assert "messages" not in body
    assert body["reasoning"] == {"effort": "low"}
    assert body["max_output_tokens"] == 4_096
    assert body["text"]["format"]["type"] == "json_schema"
    schema = body["text"]["format"]["schema"]
    assert schema["title"] == "VisualCandidateExtractionResult"
    assert "temporal_signals" in schema["properties"]
    assert "start" not in json.dumps(schema)
    assert "relations" not in schema["properties"]


@pytest.mark.asyncio
async def test_openai_compatible_provider_requests_structured_json() -> None:
    async def respond(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://llm.example/v1/chat/completions"
        assert request.headers["Authorization"] == "Bearer secret"
        body = json.loads(request.content)
        assert body["model"] == "model-v1"
        assert body["response_format"] == {"type": "json_object"}
        assert "沈砚黑发" in body["messages"][1]["content"]
        assert "hair.color" in body["messages"][0]["content"]
        assert "mention_quote" in body["messages"][0]["content"]
        assert "Do not calculate character offsets" in body["messages"][0]["content"]
        assert "combined appearance field" in body["messages"][0]["content"]
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "entities": [
                                        {
                                            "local_id": "e1",
                                            "representative_name": "沈砚",
                                            "mention_quote": "沈砚",
                                            "mention_kind": "name",
                                            "confidence": 0.95,
                                        }
                                    ],
                                    "visual_candidates": [
                                        {
                                            "entity_ref": "e1",
                                            "field_path": "hair.color",
                                            "value": "黑色",
                                            "evidence_quote": "黑发",
                                            "epistemic_status": "asserted",
                                            "confidence": 0.9,
                                            "temporal_signals": [],
                                        }
                                    ],
                                    "deferred_items": [],
                                }
                            )
                        }
                    }
                ]
            },
        )

    provider = OpenAICompatibleExtractionProvider(
        provider="deepseek",
        base_url="https://llm.example/v1",
        api_key="secret",
        model="model-v1",
        transport=httpx.MockTransport(respond),
    )
    result = await provider.extract_chunk("沈砚黑发")
    assert result.entities[0].representative_name == "沈砚"
    assert result.visual_candidates[0].evidence_quote == "黑发"
    assert provider.version == (
        "deepseek:model-v1:visual-observation-v3.4:visual-extraction-prompt-v2.5"
    )


def test_provider_can_freeze_a_prompt_variant_for_ab_and_rollback() -> None:
    provider = OpenAICompatibleExtractionProvider(
        provider="deepseek",
        base_url="https://llm.example/v1",
        api_key="secret",
        model="model-v1",
        system_prompt=EXTRACTION_SYSTEM_PROMPT_V2_5,
        prompt_version="visual-extraction-prompt-v2.5",
    )

    body = provider._request_body("少女佩戴玉坠。")

    assert body["messages"][0]["content"] == EXTRACTION_SYSTEM_PROMPT_V2_5
    assert provider.version.endswith(":visual-observation-v3.4:visual-extraction-prompt-v2.5")


def test_provider_payload_normalizes_common_epistemic_aliases() -> None:
    result = validate_provider_visual_candidate_payload(
        {
            "entities": [
                {
                    "local_id": "e1",
                    "representative_name": "沈砚",
                    "mention_quote": "沈砚",
                    "mention_kind": "name",
                    "confidence": 0.9,
                }
            ],
            "visual_candidates": [
                {
                    "entity_ref": "e1",
                    "field_path": "hair.color",
                    "value": "黑色",
                    "evidence_quote": "沈砚黑发",
                    "epistemic_status": "explicit",
                    "confidence": 0.9,
                }
            ],
        }
    )

    assert result.visual_candidates[0].epistemic_status == "asserted"
    assert result.entities[0].mention_kind == "explicit_name"


def test_provider_schema_exposes_only_r1_mention_kinds_and_normalizes_legacy_labels() -> None:
    schema = build_chunk_extraction_request(
        "少女佩戴玉坠。",
        model="model-v1",
        wire_api="responses",
    )["text"]["format"]["schema"]
    definition = schema["$defs"]["VisualEntityCandidate"]
    assert definition["properties"]["mention_kind"]["enum"] == [
        "explicit_name",
        "descriptor",
        "pronoun",
        "unknown",
    ]
    deferred_reasons = schema["$defs"]["VisualDeferredCandidate"]["properties"][
        "reason_code"
    ]["enum"]
    assert "inferred_visual_fact" in deferred_reasons
    assert "uncertain_visual_fact" in deferred_reasons

    legacy = validate_provider_visual_candidate_payload(
        {
            "entities": [
                {
                    "local_id": "e1",
                    "representative_name": "少女",
                    "mention_quote": "少女",
                    "mention_kind": "title",
                    "confidence": 0.9,
                }
            ]
        }
    )

    assert legacy.entities[0].mention_kind == "descriptor"


@pytest.mark.parametrize(
    "mention_kind",
    ["explicit_name", "descriptor", "pronoun", "unknown"],
)
def test_provider_accepts_each_r1_mention_kind(mention_kind: str) -> None:
    result = validate_provider_visual_candidate_payload(
        {
            "entities": [
                {
                    "local_id": "e1",
                    "representative_name": "她",
                    "mention_quote": "她",
                    "mention_kind": mention_kind,
                    "confidence": 0.9,
                }
            ]
        }
    )

    assert result.entities[0].mention_kind == mention_kind


def test_provider_payload_rejects_dangling_entity_reference() -> None:
    with pytest.raises(ValueError, match="unknown_visual_entity_ref:e2"):
        validate_provider_visual_candidate_payload(
            {
                "visual_candidates": [
                    {
                        "entity_ref": "e2",
                        "field_path": "hair.color",
                        "value": "黑色",
                        "evidence_quote": "沈砚黑发",
                        "epistemic_status": "asserted",
                        "confidence": 0.9,
                    }
                ]
            }
        )


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ('\ufeff  {"visual_candidates": []}', {"visual_candidates": []}),
        (
            '```json\n{"visual_candidates": [], "deferred_items": []}\n```',
            {"visual_candidates": [], "deferred_items": []},
        ),
        (
            '提取结果如下：\n{"visual_candidates": [{"value": "衣服上有 } 图案"}]}\n以上。',
            {"visual_candidates": [{"value": "衣服上有 } 图案"}]},
        ),
        (
            '{"visual_candidates": [], "deferred_items": [],}',
            {"visual_candidates": [], "deferred_items": []},
        ),
        (
            '"{\\"visual_candidates\\": [], \\"deferred_items\\": []}"',
            {"visual_candidates": [], "deferred_items": []},
        ),
    ],
)
def test_decode_provider_json_recovers_safe_formatting_errors(
    content: str, expected: object
) -> None:
    assert decode_provider_json(content) == expected


@pytest.mark.parametrize(
    "content",
    [
        '{"visual_candidates": [',
        "{visual_candidates: []}",
        "模型没有返回结构化数据",
    ],
)
def test_decode_provider_json_rejects_ambiguous_or_truncated_content(
    content: str,
) -> None:
    with pytest.raises(ValueError, match="invalid_provider_json"):
        decode_provider_json(content)


@pytest.mark.asyncio
async def test_provider_accepts_fenced_json_without_triggering_worker_retry() -> None:
    calls = 0

    async def respond(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": (
                                '```json\n{"entities": [], "visual_candidates": [], '
                                '"deferred_items": []}\n```'
                            )
                        }
                    }
                ]
            },
        )

    provider = OpenAICompatibleExtractionProvider(
        provider="deepseek",
        base_url="https://llm.example/v1",
        api_key="secret",
        model="model-v1",
        transport=httpx.MockTransport(respond),
    )

    result = await provider.extract_chunk("沈砚黑发")

    assert result.visual_candidates == []
    assert calls == 1


@pytest.mark.asyncio
async def test_provider_retries_length_once_and_records_usage_metadata() -> None:
    calls = 0

    async def respond(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(
                200,
                json={
                    "id": "truncated-1",
                    "choices": [{"finish_reason": "length", "message": {"content": "{}"}}],
                },
            )
        return httpx.Response(
            200,
            headers={"x-request-id": "request-2"},
            json={
                "model": "model-v1-revision",
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": '{"visual_candidates": []}'},
                    }
                ],
                "usage": {
                    "prompt_tokens": 12,
                    "completion_tokens": 4,
                    "prompt_tokens_details": {"cached_tokens": 8},
                    "completion_tokens_details": {"reasoning_tokens": 2},
                },
            },
        )

    provider = OpenAICompatibleExtractionProvider(
        provider="deepseek",
        base_url="https://llm.example/v1",
        api_key="secret",
        model="model-v1",
        max_retries=1,
        transport=httpx.MockTransport(respond),
    )

    detailed = await provider.extract_chunk_detailed("沈砚黑发")

    assert calls == 2
    assert detailed.metadata.attempts == 2
    assert detailed.metadata.provider_request_id == "request-2"
    assert detailed.metadata.response_model == "model-v1-revision"
    assert detailed.metadata.usage.input_tokens == 12
    assert detailed.metadata.usage.cache_hit_tokens == 8
    assert detailed.metadata.usage.reasoning_tokens == 2
    assert detailed.metadata.usage.total_tokens == 16
    assert detailed.raw_message_content == '{"visual_candidates": []}'
    assert detailed.raw_response["model"] == "model-v1-revision"
    assert detailed.raw_response["usage"]["completion_tokens"] == 4


@pytest.mark.asyncio
async def test_responses_provider_rejects_incomplete_and_accepts_completed_output() -> None:
    calls = 0

    async def respond(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert str(request.url) == "https://llm.example/v1/responses"
        if calls == 1:
            return httpx.Response(
                200,
                json={
                    "id": "response-1",
                    "status": "incomplete",
                    "incomplete_details": {"reason": "max_output_tokens"},
                    "output": [],
                },
            )
        return httpx.Response(
            200,
            json={
                "id": "response-2",
                "status": "completed",
                "model": "model-v1",
                "output_text": '{"visual_candidates": []}',
                "usage": {"input_tokens": 10, "output_tokens": 3, "total_tokens": 13},
            },
        )

    provider = OpenAICompatibleExtractionProvider(
        provider="deepseek",
        base_url="https://llm.example/v1",
        api_key="secret",
        model="model-v1",
        wire_api="responses",
        max_retries=1,
        transport=httpx.MockTransport(respond),
    )

    detailed = await provider.extract_chunk_detailed("沈砚黑发")

    assert detailed.metadata.wire_api == "responses"
    assert detailed.metadata.status == "completed"
    assert detailed.metadata.attempts == 2


def test_provider_enforces_collection_item_limit_before_persistence() -> None:
    with pytest.raises(ProviderExtractionError, match="provider_item_limit_exceeded"):
        validate_provider_visual_candidate_payload(
            {"visual_candidates": [{"invalid": True}, {"invalid": True}]},
            max_items_per_result=1,
        )


@pytest.mark.asyncio
async def test_provider_enforces_total_wall_clock_deadline() -> None:
    async def respond(_: httpx.Request) -> httpx.Response:
        await asyncio.sleep(0.05)
        return httpx.Response(
            200,
            json={"choices": [{"finish_reason": "stop", "message": {"content": "{}"}}]},
        )

    provider = OpenAICompatibleExtractionProvider(
        provider="deepseek",
        base_url="https://llm.example/v1",
        api_key="secret",
        model="model-v1",
        total_deadline_seconds=0.01,
        max_retries=0,
        transport=httpx.MockTransport(respond),
    )

    with pytest.raises(ProviderExtractionError, match="provider_total_deadline_exceeded"):
        await provider.extract_chunk("沈砚黑发")
