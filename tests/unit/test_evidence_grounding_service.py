from __future__ import annotations

import hashlib

from novel_character_generator.application.ports.evidence_grounding import (
    EvidenceGroundingExecutionRequest,
)
from novel_character_generator.application.ports.visual_evidence import (
    GroundedEvidenceCandidate,
    VisualEvidenceDiscoveryResult,
    VisualEvidenceMention,
)
from novel_character_generator.application.services.evidence_grounding_service import (
    EvidenceGroundingService,
)


def _request(
    chunk_text: str,
    *,
    mentions: tuple[VisualEvidenceMention, ...] = (),
    candidates: tuple[GroundedEvidenceCandidate, ...] = (),
    max_context_chars: int = 600,
) -> EvidenceGroundingExecutionRequest:
    return EvidenceGroundingExecutionRequest(
        schema_version="evidence-grounding-input-v2",
        run_id="run-1",
        source_document_version_id="source-v1",
        chunk_id="chunk-1",
        chunk_text=chunk_text,
        discovery=VisualEvidenceDiscoveryResult(
            schema_version="visual-evidence-discovery-v2",
            chunk_id="chunk-1",
            mentions=mentions,
            evidence_candidates=candidates,
        ),
        max_context_chars=max_context_chars,
    )


def _candidate(
    quote: str,
    *,
    candidate_id: str = "c1",
    owner_id: str | None = None,
) -> GroundedEvidenceCandidate:
    return GroundedEvidenceCandidate(
        candidate_id=candidate_id,
        local_owner_id=owner_id,
        evidence_quote=quote,
    )


def test_n2_v2_grounds_unique_quote_with_hash_context_and_stable_id() -> None:
    quote = "男子年龄在二十左右，英俊的相貌，配上挺拔的身材"
    text = f"众人停步。{quote}。大厅里十分安静。"
    request = _request(
        text,
        mentions=(VisualEvidenceMention(mention_id="m1", mention_quote="男子"),),
        candidates=(_candidate(quote, owner_id="m1"),),
    )

    first = EvidenceGroundingService().ground(request)
    second = EvidenceGroundingService().ground(request)

    assert first.status == "succeeded"
    assert first.counts.grounded_candidates == 1
    grounded = first.output.grounded_candidates[0]
    assert grounded.evidence_span.source_quote == quote
    assert grounded.evidence_span.quote_hash == hashlib.sha256(
        quote.encode("utf-8")
    ).hexdigest()
    assert grounded.local_context.text == f"{quote}。"
    assert (
        grounded.local_context.text[
            grounded.local_context.focus_start : grounded.local_context.focus_end
        ]
        == quote
    )
    assert grounded.candidate_id == second.output.grounded_candidates[0].candidate_id
    assert first.input_fingerprint == second.input_fingerprint
    assert first.output_fingerprint == second.output_fingerprint


def test_n2_v2_defers_repeated_verbatim_quote_without_owner_guessing() -> None:
    artifact = EvidenceGroundingService().ground(
        _request(
            "门外站着青衫老者。青衫老者转身离开。",
            mentions=(
                VisualEvidenceMention(mention_id="m1", mention_quote="青衫老者"),
            ),
            candidates=(_candidate("青衫老者", owner_id="m1"),),
        )
    )

    assert artifact.counts.grounded_candidates == 0
    assert artifact.output.mention_nodes[0].grounding_status == "ambiguous"
    assert artifact.output.deferred_items[0].reason_code == "ambiguous_evidence"
    assert artifact.output.deferred_items[0].occurrence_count == 2


def test_n2_v2_rejects_non_verbatim_and_punctuation_rewrites() -> None:
    artifact = EvidenceGroundingService().ground(
        _request(
            "第一句。第二句。",
            candidates=(
                _candidate("第一句，第二句。", candidate_id="c1"),
                _candidate("模型改写而非原文", candidate_id="c2"),
            ),
        )
    )

    assert [item.reason_code for item in artifact.output.rejected_items] == [
        "quote_not_in_chunk",
        "quote_not_in_chunk",
    ]
    assert artifact.output.deferred_items == ()


def test_n2_v2_accepts_only_whitespace_difference_and_restores_source_slice() -> None:
    artifact = EvidenceGroundingService().ground(
        _request(
            "段首。第一句。\n　　第二句。段尾。",
            candidates=(_candidate("第一句。第二句。"),),
        )
    )

    grounded = artifact.output.grounded_candidates[0]
    assert grounded.grounding_status == "whitespace_unique"
    assert grounded.evidence_quote == "第一句。\n　　第二句。"
    assert grounded.evidence_span.source_quote == "第一句。\n　　第二句。"


def test_n2_v2_rejects_duplicate_candidate_after_canonicalization() -> None:
    artifact = EvidenceGroundingService().ground(
        _request(
            "第一句。\n第二句。",
            candidates=(
                _candidate("第一句。第二句。", candidate_id="c1"),
                _candidate("第一句。\n第二句。", candidate_id="c2"),
            ),
        )
    )

    assert artifact.counts.grounded_candidates == 1
    assert artifact.output.rejected_items[0].reason_code == "deterministic_duplicate"


def test_n2_v2_defers_when_quote_exceeds_context_budget() -> None:
    quote = "高" * 65
    artifact = EvidenceGroundingService().ground(
        _request(f"男子{quote}。", candidates=(_candidate(quote),), max_context_chars=64)
    )

    assert artifact.output.deferred_items[0].reason_code == (
        "local_context_budget_exceeded"
    )
