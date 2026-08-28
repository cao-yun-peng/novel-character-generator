from __future__ import annotations

import pytest
from pydantic import ValidationError

from novel_character_generator.application.ports.local_grounding import (
    GroundedEvidenceSpan,
    LocalContextWindow,
    LocalGroundingExecutionRequest,
)
from novel_character_generator.application.ports.local_observation import (
    LocalObservationDiscoveryResult,
)


def _empty_discovery(*, chunk_id: str = "chunk-1") -> LocalObservationDiscoveryResult:
    return LocalObservationDiscoveryResult(
        schema_version="local-observation-discovery-v1.1",
        chunk_id=chunk_id,
        entities=[],
        facts=[],
        temporal_signals=[],
        unresolved_items=[],
    )


def test_n2_request_rejects_cross_chunk_discovery() -> None:
    with pytest.raises(ValidationError, match="local_grounding_chunk_id_mismatch"):
        LocalGroundingExecutionRequest(
            schema_version="local-grounding-input-v1",
            run_id="run-1",
            source_document_version_id="source-v1",
            chunk_id="chunk-1",
            chunk_text="正文",
            discovery=_empty_discovery(chunk_id="chunk-2"),
        )


def test_n2_context_contract_rejects_focus_outside_window() -> None:
    with pytest.raises(ValidationError, match="local_context_focus_out_of_range"):
        LocalContextWindow(
            policy_version="local-context-sentence-window-v1",
            start=0,
            end=2,
            text="正文",
            focus_start=0,
            focus_end=3,
            context_hash="0" * 64,
        )


def test_n2_evidence_contract_rejects_reversed_span() -> None:
    with pytest.raises(ValidationError):
        GroundedEvidenceSpan(
            start=3,
            end=2,
            source_quote="正文",
            quote_hash="0" * 64,
        )
