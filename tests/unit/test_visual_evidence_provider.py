import json
from pathlib import Path

import httpx
import pytest

from novel_character_generator.application.ports.visual_evidence import (
    VISUAL_EVIDENCE_PROMPT_VERSION,
    VisualEvidenceDiscoveryInput,
    VisualEvidenceModelCandidate,
    VisualEvidenceModelMention,
    VisualEvidenceModelOutput,
)
from novel_character_generator.infrastructure.llm.visual_evidence import (
    VISUAL_EVIDENCE_SYSTEM_PROMPT,
    OpenAICompatibleVisualEvidenceProvider,
    build_visual_evidence_request,
)


def _request() -> VisualEvidenceDiscoveryInput:
    return VisualEvidenceDiscoveryInput(
        schema_version="visual-evidence-discovery-input-v2",
        chunk_id="chunk-1",
        chunk_text="沈砚留着黑色短发。",
        previous_tail="上一段有一顶帽子。",
    )


def _payload() -> dict[str, object]:
    return {
        "mentions": [{"mention_quote": "沈砚"}],
        "evidence_candidates": [{"owner_index": 0, "evidence_quote": "黑色短发"}],
    }


def test_m1_v2_request_sends_only_current_chunk() -> None:
    body = build_visual_evidence_request(_request(), model="model-v2")
    serialized = json.dumps(body, ensure_ascii=False)
    user_content = body["messages"][1]["content"]
    assert "沈砚留着黑色短发。" in user_content
    assert "chunk-1" not in user_content
    assert "上一段有一顶帽子" not in serialized
    assert "previous_tail" not in user_content
    assert "raw_proposition" not in serialized
    assert "coarse_family" not in serialized
    assert "owner_index" in serialized
    assert body["temperature"] == 0


def test_m1_v2_wire_schema_has_no_semantic_fields() -> None:
    rendered = json.dumps(VisualEvidenceModelOutput.model_json_schema())
    for field in (
        "category",
        "coarse_family",
        "raw_proposition",
        "epistemic_status",
        "signal_kind",
    ):
        assert field not in rendered


def test_m1_v2_wire_schema_matches_registry_shape() -> None:
    registry = json.loads(
        Path("docs/contracts/semantic-pipeline-v2-model-schemas.json").read_text(
            encoding="utf-8"
        )
    )
    runtime = VisualEvidenceModelOutput.model_json_schema()
    registry_output = registry["$defs"]["VisualEvidenceDiscoveryOutput"]
    assert set(runtime["properties"]) == set(registry_output["properties"])
    assert set(VisualEvidenceModelMention.model_json_schema()["properties"]) == {"mention_quote"}
    assert set(VisualEvidenceModelCandidate.model_json_schema()["properties"]) == {
        "owner_index",
        "evidence_quote",
    }


def test_m1_v2_prompt_forbids_classification() -> None:
    assert VISUAL_EVIDENCE_PROMPT_VERSION == "visual-evidence-discovery-prompt-v2.8"
    assert "evidence discovery" in VISUAL_EVIDENCE_SYSTEM_PROMPT
    assert "categories" in VISUAL_EVIDENCE_SYSTEM_PROMPT
    assert "A statement that a visible feature is absent" in VISUAL_EVIDENCE_SYSTEM_PROMPT
    assert '"Minimal" never means "the shortest fragment."' in VISUAL_EVIDENCE_SYSTEM_PROMPT
    assert "preserve the continuous relation" in VISUAL_EVIDENCE_SYSTEM_PROMPT
    assert "complete basis-to-conclusion relation" in VISUAL_EVIDENCE_SYSTEM_PROMPT
    assert "not itself a character mention" in VISUAL_EVIDENCE_SYSTEM_PROMPT
    assert "Do not manufacture an owner" in VISUAL_EVIDENCE_SYSTEM_PROMPT
    assert "must positively identify one specific local character" in (
        VISUAL_EVIDENCE_SYSTEM_PROMPT
    )
    assert "uncertainty about who owns the evidence requires owner_index=null" in (
        VISUAL_EVIDENCE_SYSTEM_PROMPT
    )
    assert "Construct every evidence_quote with two boundaries" in (
        VISUAL_EVIDENCE_SYSTEM_PROMPT
    )
    assert "A unique owner mention or owner_index does not repair" in (
        VISUAL_EVIDENCE_SYSTEM_PROMPT
    )
    assert "perform a second clause-by-clause coverage sweep" in (
        VISUAL_EVIDENCE_SYSTEM_PROMPT
    )
    assert "embedded inside a perception phrase, an action beat, a dialogue tag" in (
        VISUAL_EVIDENCE_SYSTEM_PROMPT
    )
    assert "Different visible features do not substitute for one another" in (
        VISUAL_EVIDENCE_SYSTEM_PROMPT
    )
    assert "An owner transition is a hard candidate boundary" in (
        VISUAL_EVIDENCE_SYSTEM_PROMPT
    )
    assert "appearance facts about at most one local person" in (
        VISUAL_EVIDENCE_SYSTEM_PROMPT
    )
    assert "form one compound candidate" in VISUAL_EVIDENCE_SYSTEM_PROMPT
    assert "does not require one candidate per clause" in VISUAL_EVIDENCE_SYSTEM_PROMPT
    assert "do not promote a pure action, speech, or emotion clause" in (
        VISUAL_EVIDENCE_SYSTEM_PROMPT
    )
    assert "Uniqueness is a hard output invariant" not in VISUAL_EVIDENCE_SYSTEM_PROMPT
    assert "each distinct visual predicate" not in VISUAL_EVIDENCE_SYSTEM_PROMPT


@pytest.mark.asyncio
async def test_m1_v2_provider_materializes_deterministic_ids() -> None:
    async def respond(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": json.dumps(_payload())}}]},
        )

    provider = OpenAICompatibleVisualEvidenceProvider(
        provider="deepseek",
        base_url="https://llm.example/v1",
        api_key="secret",
        model="model-v2",
        transport=httpx.MockTransport(respond),
    )
    detailed = await provider.discover_detailed(_request())
    assert detailed.output.chunk_id == "chunk-1"
    assert detailed.output.mentions[0].mention_id == "m1"
    assert detailed.output.evidence_candidates[0].candidate_id == "c1"
    assert detailed.output.evidence_candidates[0].local_owner_id == "m1"
    assert len(provider.prompt_hash) == 64
