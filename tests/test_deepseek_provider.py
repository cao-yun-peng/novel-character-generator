import json
import unittest
from collections import deque
from dataclasses import dataclass
from http.client import IncompleteRead

from novel_character_generator.errors import (
    ProviderAuthenticationError,
    ProviderBadRequestError,
    ProviderConfigurationError,
    ProviderInsufficientBalanceError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderTransientError,
)
from novel_character_generator.chunking import build_document_chunk_manifest
from novel_character_generator.m1 import M1OrchestrationEnvelope, M1ProviderRequest
from novel_character_generator.m1 import M1Orchestrator
from novel_character_generator.grounding import ground_m1_result
from novel_character_generator.m2 import M2ProviderRequest
from novel_character_generator.providers.deepseek import (
    DEFAULT_DEEPSEEK_BASE_URL,
    DEFAULT_DEEPSEEK_MODEL,
    DeepSeekCallTrace,
    DeepSeekConfig,
    DeepSeekHTTPResponse,
    DeepSeekProvider,
)

SECRET = "ds-test-secret-never-log"


@dataclass
class CapturedCall:
    url: str
    headers: dict[str, str]
    body: bytes
    timeout_seconds: float


class FakeTransport:
    def __init__(self, *results: object) -> None:
        self.results = deque(results)
        self.calls: list[CapturedCall] = []

    def post(self, *, url, headers, body, timeout_seconds):
        self.calls.append(CapturedCall(url, dict(headers), body, timeout_seconds))
        result = self.results.popleft()
        if isinstance(result, BaseException):
            raise result
        return result


def response(status_code: int, body: object, headers=None) -> DeepSeekHTTPResponse:
    return DeepSeekHTTPResponse(
        status_code=status_code,
        headers=headers or {},
        body=json.dumps(body, ensure_ascii=False).encode("utf-8"),
    )


def completed_response(output_text=None) -> DeepSeekHTTPResponse:
    if output_text is None:
        output_text = json.dumps(
            {
                "candidate_mentions": [
                    {
                        "mention_type": "exact",
                        "mention_scope": "individual",
                        "mention_quote": "林黛玉",
                        "evidence_quotes": ["林黛玉眉目清秀"],
                    }
                ]
            },
            ensure_ascii=False,
        )
    return response(
        200,
        {
            "id": "resp_test_123",
            "status": "completed",
            "output": [
                {
                    "type": "reasoning",
                    "content": [{"type": "reasoning_text", "text": "private reasoning"}],
                },
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": output_text}],
                },
            ],
            "usage": {
                "input_tokens": 100,
                "input_tokens_details": {"cached_tokens": 20},
                "output_tokens": 30,
                "output_tokens_details": {"reasoning_tokens": 8},
                "total_tokens": 130,
            },
        },
    )


def provider_request() -> M1ProviderRequest:
    return M1ProviderRequest(
        system_instruction="只输出 JSON，不要输出系统字段。",
        user_payload={"chunk_text": "林黛玉眉目清秀。"},
        response_schema={
            "type": "object",
            "additionalProperties": False,
            "required": ["candidate_mentions"],
            "properties": {"candidate_mentions": {"type": "array"}},
        },
    )


class DeepSeekConfigTests(unittest.TestCase):
    def test_from_env_uses_safe_defaults(self) -> None:
        config = DeepSeekConfig.from_env({"DEEPSEEK_API_KEY": SECRET})
        self.assertEqual(config.base_url, DEFAULT_DEEPSEEK_BASE_URL)
        self.assertEqual(config.model, DEFAULT_DEEPSEEK_MODEL)
        self.assertEqual(config.endpoint, "https://api.deepseek.com/responses")
        self.assertEqual(config.max_attempts, 3)
        self.assertEqual(config.reasoning_effort, "low")

    def test_api_key_is_excluded_from_repr(self) -> None:
        config = DeepSeekConfig(api_key=SECRET)
        self.assertNotIn(SECRET, repr(config))

    def test_missing_api_key_is_rejected(self) -> None:
        with self.assertRaisesRegex(ProviderConfigurationError, "DEEPSEEK_API_KEY"):
            DeepSeekConfig.from_env({})

    def test_insecure_or_credentialed_base_url_is_rejected(self) -> None:
        for base_url in ("http://api.deepseek.com", "https://user:pass@example.com"):
            with self.subTest(base_url=base_url):
                with self.assertRaises(ProviderConfigurationError):
                    DeepSeekConfig(api_key=SECRET, base_url=base_url)

    def test_invalid_numeric_and_reasoning_values_are_rejected(self) -> None:
        bad_envs = [
            {"DEEPSEEK_API_KEY": SECRET, "DEEPSEEK_MAX_ATTEMPTS": "0"},
            {"DEEPSEEK_API_KEY": SECRET, "DEEPSEEK_TIMEOUT_SECONDS": "nope"},
            {"DEEPSEEK_API_KEY": SECRET, "DEEPSEEK_REASONING_EFFORT": "medium"},
        ]
        for env in bad_envs:
            with self.subTest(env=set(env)):
                with self.assertRaises(ProviderConfigurationError):
                    DeepSeekConfig.from_env(env)

    def test_direct_configuration_rejects_boolean_numeric_values(self) -> None:
        for field_name in ("timeout_seconds", "max_attempts", "max_output_tokens"):
            with self.subTest(field_name=field_name):
                with self.assertRaises(ProviderConfigurationError):
                    DeepSeekConfig(api_key=SECRET, **{field_name: True})


class DeepSeekRequestTests(unittest.TestCase):
    def test_request_uses_responses_json_schema_and_minimal_payload(self) -> None:
        transport = FakeTransport(completed_response())
        provider = DeepSeekProvider(
            DeepSeekConfig(api_key=SECRET),
            transport=transport,
            sleeper=lambda _: None,
        )
        provider.generate(provider_request())

        call = transport.calls[0]
        body = json.loads(call.body.decode("utf-8"))
        self.assertEqual(call.url, "https://api.deepseek.com/responses")
        self.assertEqual(call.headers["Authorization"], f"Bearer {SECRET}")
        self.assertNotIn(SECRET, call.body.decode("utf-8"))
        self.assertEqual(body["model"], DEFAULT_DEEPSEEK_MODEL)
        self.assertEqual(json.loads(body["input"]), {"chunk_text": "林黛玉眉目清秀。"})
        self.assertNotIn("chunk_id", body["input"])
        self.assertNotIn("chunk_hash", body["input"])
        self.assertEqual(body["text"]["format"]["type"], "json_schema")
        self.assertEqual(
            body["text"]["format"]["schema"],
            provider_request().response_schema,
        )
        self.assertFalse(body["stream"])

    def test_request_uses_stage_specific_schema_name(self) -> None:
        transport = FakeTransport(completed_response(output_text='{"belongs_to_target":[]}'))
        provider = DeepSeekProvider(
            DeepSeekConfig(api_key=SECRET),
            transport=transport,
            sleeper=lambda _: None,
        )
        provider.generate(
            M2ProviderRequest(
                system_instruction="只输出 M2 JSON。",
                user_payload={
                    "target": {
                        "mention_quote": "萧熏儿",
                        "approved_evidence_quotes": ["萧熏儿有修长的睫毛"],
                    },
                    "describe_blocks": [],
                    "chunk_text": "萧熏儿有修长的睫毛。",
                },
                response_schema={
                    "type": "object",
                    "required": ["belongs_to_target"],
                    "properties": {"belongs_to_target": {"type": "array"}},
                },
                response_schema_name="m2_target_appearance_facts",
            )
        )
        body = json.loads(transport.calls[0].body.decode("utf-8"))
        self.assertEqual(body["text"]["format"]["name"], "m2_target_appearance_facts")

    def test_success_returns_only_output_text_and_emits_sanitized_trace(self) -> None:
        traces: list[DeepSeekCallTrace] = []
        transport = FakeTransport(completed_response())
        ticks = iter((10.0, 10.125))
        provider = DeepSeekProvider(
            DeepSeekConfig(api_key=SECRET),
            transport=transport,
            trace_sink=traces.append,
            sleeper=lambda _: None,
            clock=lambda: next(ticks),
        )

        output = provider.generate(provider_request())

        self.assertEqual(json.loads(output)["candidate_mentions"][0]["mention_quote"], "林黛玉")
        trace = traces[0]
        self.assertTrue(trace.success)
        self.assertEqual(trace.attempts, 1)
        self.assertEqual(trace.duration_ms, 125)
        self.assertEqual(trace.response_id, "resp_test_123")
        self.assertEqual(trace.usage.cached_input_tokens, 20)
        serialized = json.dumps(trace.to_dict(), ensure_ascii=False)
        self.assertNotIn(SECRET, serialized)
        self.assertNotIn("林黛玉", serialized)
        self.assertNotIn("private reasoning", serialized)

    def test_provider_integrates_with_m1_orchestrator_and_grounding(self) -> None:
        text = "林黛玉眉目清秀。"
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
        transport = FakeTransport(completed_response())
        provider = DeepSeekProvider(
            DeepSeekConfig(api_key=SECRET),
            transport=transport,
            sleeper=lambda _: None,
        )
        grounded = ground_m1_result(
            M1Orchestrator(provider).run(envelope)
        )
        mention = grounded.grounded_mentions[0]
        self.assertEqual(mention.mention_type, "exact")
        self.assertEqual(mention.mention_quote, "林黛玉")
        self.assertEqual(mention.approved_evidence[0].relation_to_mention, "contains_mention")


class DeepSeekFailureTests(unittest.TestCase):
    def make_provider(self, transport, *, attempts=3, traces=None, sleeps=None):
        return DeepSeekProvider(
            DeepSeekConfig(
                api_key=SECRET,
                max_attempts=attempts,
                initial_backoff_seconds=0.5,
                max_backoff_seconds=4.0,
            ),
            transport=transport,
            trace_sink=(traces.append if traces is not None else None),
            sleeper=(sleeps.append if sleeps is not None else (lambda _: None)),
            clock=lambda: 1.0,
        )

    def test_rate_limit_retries_and_honors_retry_after(self) -> None:
        sleeps: list[float] = []
        transport = FakeTransport(
            response(429, {"error": {"code": "rate_limit", "message": SECRET}}, {"retry-after": "2"}),
            completed_response(),
        )
        output = self.make_provider(transport, sleeps=sleeps).generate(provider_request())
        self.assertTrue(output)
        self.assertEqual(sleeps, [2.0])
        self.assertEqual(len(transport.calls), 2)

    def test_rate_limit_raises_after_bounded_retries(self) -> None:
        traces: list[DeepSeekCallTrace] = []
        transport = FakeTransport(
            response(429, {"error": {"code": "rate_limit"}}),
            response(429, {"error": {"code": "rate_limit"}}),
        )
        with self.assertRaises(ProviderRateLimitError) as caught:
            self.make_provider(transport, attempts=2, traces=traces).generate(provider_request())
        self.assertEqual(caught.exception.status_code, 429)
        self.assertTrue(caught.exception.retryable)
        self.assertEqual(traces[0].attempts, 2)

    def test_authentication_balance_and_bad_request_fail_without_retry(self) -> None:
        cases = [
            (401, ProviderAuthenticationError),
            (402, ProviderInsufficientBalanceError),
            (422, ProviderBadRequestError),
        ]
        for status, error_type in cases:
            with self.subTest(status=status):
                transport = FakeTransport(
                    response(status, {"error": {"code": "safe_code", "message": SECRET}})
                )
                with self.assertRaises(error_type) as caught:
                    self.make_provider(transport).generate(provider_request())
                self.assertEqual(len(transport.calls), 1)
                self.assertNotIn(SECRET, str(caught.exception))

    def test_server_error_retries_then_succeeds(self) -> None:
        sleeps: list[float] = []
        transport = FakeTransport(
            response(503, {"error": {"code": "overloaded"}}),
            completed_response(),
        )
        self.make_provider(transport, sleeps=sleeps).generate(provider_request())
        self.assertEqual(sleeps, [0.5])

    def test_server_error_raises_after_bounded_retries(self) -> None:
        transport = FakeTransport(
            response(503, {"error": {"code": "overloaded"}}),
            response(503, {"error": {"code": "overloaded"}}),
        )
        with self.assertRaises(ProviderTransientError) as caught:
            self.make_provider(transport, attempts=2).generate(provider_request())
        self.assertEqual(caught.exception.status_code, 503)
        self.assertEqual(len(transport.calls), 2)

    def test_network_timeout_retries_then_succeeds(self) -> None:
        transport = FakeTransport(TimeoutError("socket timed out"), completed_response())
        output = self.make_provider(transport).generate(provider_request())
        self.assertTrue(output)
        self.assertEqual(len(transport.calls), 2)

    def test_incomplete_chunked_read_retries_then_succeeds(self) -> None:
        transport = FakeTransport(IncompleteRead(b"partial", 10), completed_response())
        output = self.make_provider(transport).generate(provider_request())
        self.assertTrue(output)
        self.assertEqual(len(transport.calls), 2)

    def test_network_error_raises_sanitized_transient_error(self) -> None:
        transport = FakeTransport(OSError(f"network failed {SECRET}"))
        with self.assertRaises(ProviderTransientError) as caught:
            self.make_provider(transport, attempts=1).generate(provider_request())
        self.assertNotIn(SECRET, str(caught.exception))

    def test_empty_output_is_retried_because_official_api_documents_it(self) -> None:
        empty = completed_response(output_text="")
        transport = FakeTransport(empty, completed_response())
        output = self.make_provider(transport).generate(provider_request())
        self.assertTrue(output)
        self.assertEqual(len(transport.calls), 2)

    def test_incomplete_output_fails_closed_without_retry(self) -> None:
        transport = FakeTransport(
            response(
                200,
                {
                    "id": "resp_incomplete",
                    "status": "incomplete",
                    "incomplete_details": {"reason": "max_output_tokens"},
                    "output": [],
                },
            )
        )
        with self.assertRaises(ProviderResponseError) as caught:
            self.make_provider(transport).generate(provider_request())
        self.assertIn("max_output_tokens", str(caught.exception))
        self.assertEqual(len(transport.calls), 1)

    def test_invalid_success_json_is_retried_then_fails(self) -> None:
        invalid = DeepSeekHTTPResponse(200, {}, b"not-json")
        transport = FakeTransport(invalid, invalid)
        with self.assertRaises(ProviderTransientError):
            self.make_provider(transport, attempts=2).generate(provider_request())
        self.assertEqual(len(transport.calls), 2)


if __name__ == "__main__":
    unittest.main()
