from dataclasses import replace

import pytest

from novel_character_generator.errors import ContractValidationError
from novel_character_generator.m1 import M1ProviderRequest
from novel_character_generator.providers.deepseek import DeepSeekConfig, DeepSeekProvider
from novel_character_generator.request_cache import request_fingerprint, validate_cached_request


def test_request_identity_tracks_generation_but_not_credentials_or_retry_controls():
    config = DeepSeekConfig(api_key="test-secret")
    request = M1ProviderRequest("instruction", {"chunk_text": "source"}, {"type": "object"})
    original = request_fingerprint(DeepSeekProvider(config), request)
    assert original == request_fingerprint(
        DeepSeekProvider(replace(config, api_key="rotated", timeout_seconds=10, max_attempts=7)), request)
    for changes in ({"model": "other-model"}, {"max_output_tokens": 8192},
                    {"reasoning_effort": "high"}, {"base_url": "https://other.example"}):
        assert original != request_fingerprint(DeepSeekProvider(replace(config, **changes)), request)
    for changes in ({"system_instruction": "new"}, {"user_payload": {"chunk_text": "changed"}},
                    {"response_schema": {"type": "array"}}, {"response_schema_name": "new-schema"}):
        assert original != request_fingerprint(DeepSeekProvider(config), replace(request, **changes))
    assert "test-secret" not in str(DeepSeekProvider(config).cache_identity)


def test_unversioned_or_stale_cache_cannot_silently_resume():
    request = M1ProviderRequest("instruction", {}, {})
    assert request_fingerprint(object(), request) is None
    for saved, current in (({}, None), ({}, "a" * 64), ({"request_fingerprint": "b" * 64}, "a" * 64)):
        with pytest.raises(ContractValidationError, match="fingerprint"):
            validate_cached_request(saved, current)
    validate_cached_request({"request_fingerprint": "a" * 64}, "a" * 64)
