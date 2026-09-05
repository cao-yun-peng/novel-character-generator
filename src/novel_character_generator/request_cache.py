"""Provider request identity, independent of deterministic grounding policy."""
from __future__ import annotations

import json
from hashlib import sha256
from typing import Mapping

from .errors import ContractValidationError


def request_fingerprint(provider: object, request: object) -> str | None:
    """Unversioned custom providers can run, but cannot silently resume a cache."""
    identity = getattr(provider, "cache_identity", None)
    if identity is None:
        return None
    if not isinstance(identity, Mapping) or not identity:
        raise ContractValidationError("provider cache_identity must be a non-empty mapping")
    payload = {
        "version": "provider-request-fingerprint-v1",
        "provider": dict(identity),
        "system_instruction": request.system_instruction,
        "user_payload": request.user_payload,
        "response_schema": request.response_schema,
        "response_schema_name": request.response_schema_name,
    }
    try:
        serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                                separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ContractValidationError("request identity must be JSON serializable") from exc
    return sha256(serialized.encode("utf-8")).hexdigest()


def validate_cached_request(saved: Mapping[str, object], fingerprint: str | None) -> None:
    if fingerprint is None or saved.get("request_fingerprint") != fingerprint:
        raise ContractValidationError(
            "cached request fingerprint is missing or changed; use a new output directory "
            "for regeneration, or explicitly replay saved model outputs"
        )
