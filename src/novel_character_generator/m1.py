from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from typing import Any, Mapping, Protocol, runtime_checkable

from .chunking import ChunkManifestEntry
from .errors import ContractValidationError
from .text import SourceSpan, sha256_text

M1_ENVELOPE_VERSION = "m1-orchestration-envelope-v3"

M1_SYSTEM_INSTRUCTION = """
你负责从一个中文小说正文片段中发现人物提及，并高召回地归拢可能包含该人物可见外貌信息的连续原文证据。

严格遵守以下规则：

1. 只使用 user payload 中的 chunk_text。所有 mention_quote 和 evidence_quote 必须逐字复制原文，不补写、不改写、不概括。

2. mention_type 只能是 exact、describe 或 JSON null；mention_scope 只能是 individual、collective 或 JSON null。

3. exact 仅用于正式姓名，或文中作为固定专名使用、能够独立指向特定人物的稳定昵称/称号。
   主要由身份、职业、排行、性别、年龄、衣着、外貌或其他开放描述构成的称呼一律用 describe。
   无法确定时一律用 describe。

4. describe 是能够在原文中逐字抽取的人物泛称、身份称呼或描述性称呼，例如“老者”“少女”“红衣女子”“青衫老人”。
   只有在完全没有可逐字抽取的人物称呼、但存在人物外貌证据时，才使用 mention_type=null 且 mention_quote=null。

5. mention_scope 表示这段称呼指向单个人还是一组人：
   - exact 必须使用 individual；
   - describe 可使用 individual 或 collective；
   - “十七道白色的身影”“众人”“一群侍卫”等群体称呼必须使用 collective；
   - mention_type=null 时 mention_scope=null。

6. 优先抽取最小人物提及，避免把姓名和泛称粘成一个块。
   例如“林黛玉这女子”应拆出 exact“林黛玉”和 describe“这女子”；相关 evidence 可以同时进入两个块。

7. evidence_quote 只收录可能包含可见人物外貌信息的连续原文，包括但不限于年龄外观、面部、五官、头发、肤色、体型、身高、衣着、配饰、伤痕、体表特征及可见外观变化。
   纯动作、对白、心理、性格、身份关系、能力或背景信息，不单独作为 evidence。

8. evidence_quote 不要求包含 mention_quote。
   可以根据当前 Chunk 的局部上下文，将可能与某个 mention 有关的外貌原文收录到该提及块中。
   如果归属不确定，允许同一 evidence_quote 同时出现在多个 candidate mention 块中。
   不要为了强行唯一归属而降低召回。

9. 一个 mention 可以有多条 evidence_quote；每条 evidence_quote 应保持语义和语法上完整，并尽量去掉与外貌无关的外围文字，但不要删掉否定、比较、推断、年龄、变化或其他决定外貌含义的必要上下文。

10. 不做外貌字段分类、事实原子化、跨 Chunk 身份合并、代词最终归属、时间作用域判断、人物记忆或系统元数据生成。

11. 只输出 response schema 允许的 JSON；不要输出解释文字。
"""

M1_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["candidate_mentions"],
    "properties": {
        "candidate_mentions": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["mention_type", "mention_scope", "mention_quote", "evidence_quotes"],
                "properties": {
                    "mention_type": {"type": ["string", "null"], "enum": ["exact", "describe", None]},
                    "mention_scope": {
                        "type": ["string", "null"],
                        "enum": ["individual", "collective", None],
                    },
                    "mention_quote": {"type": ["string", "null"], "minLength": 1},
                    "evidence_quotes": {
                        "type": "array",
                        "minItems": 1,
                        "uniqueItems": True,
                        "items": {"type": "string", "minLength": 1},
                    },
                },
                "allOf": [
                    {
                        "if": {"properties": {"mention_type": {"const": None}}},
                        "then": {
                            "properties": {
                                "mention_scope": {"type": "null"},
                                "mention_quote": {"type": "null"},
                            }
                        },
                    },
                    {
                        "if": {"properties": {"mention_type": {"const": "exact"}}},
                        "then": {
                            "properties": {
                                "mention_scope": {"const": "individual"},
                                "mention_quote": {"type": "string", "minLength": 1},
                            }
                        },
                    },
                    {
                        "if": {"properties": {"mention_type": {"const": "describe"}}},
                        "then": {
                            "properties": {
                                "mention_scope": {"enum": ["individual", "collective"]},
                                "mention_quote": {"type": "string", "minLength": 1},
                            }
                        },
                    },
                ],
            },
        }
    },
}


def _expect_exact_keys(value: Mapping[str, Any], keys: set[str], *, label: str) -> None:
    actual = set(value)
    if actual != keys:
        extra = sorted(actual - keys)
        missing = sorted(keys - actual)
        raise ContractValidationError(f"{label} fields mismatch; missing={missing}, extra={extra}")


@dataclass(frozen=True)
class M1ModelInput:
    chunk_text: str

    def __post_init__(self) -> None:
        if not isinstance(self.chunk_text, str) or not self.chunk_text:
            raise ContractValidationError("M1 chunk_text must be a non-empty string")

    def to_dict(self) -> dict[str, str]:
        return {"chunk_text": self.chunk_text}


@dataclass(frozen=True)
class M1OrchestrationEnvelope:
    source_document_version_id: str
    chunking_policy_version: str
    chunk_id: str
    chunk_hash: str
    chunk_source_span: SourceSpan
    model_input: M1ModelInput
    schema_version: str = M1_ENVELOPE_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != M1_ENVELOPE_VERSION:
            raise ContractValidationError("unsupported M1 envelope schema_version")
        if not self.source_document_version_id or not self.chunking_policy_version or not self.chunk_id:
            raise ContractValidationError("M1 envelope identity fields must be non-empty")
        if self.chunk_hash != sha256_text(self.model_input.chunk_text):
            raise ContractValidationError("M1 chunk_hash does not match raw chunk_text")
        if self.chunk_source_span.end - self.chunk_source_span.start != len(self.model_input.chunk_text):
            raise ContractValidationError("M1 chunk_source_span length does not match chunk_text")

    @classmethod
    def from_manifest_entry(
        cls,
        *,
        source_document_version_id: str,
        chunking_policy_version: str,
        entry: ChunkManifestEntry,
        document_text: str,
    ) -> M1OrchestrationEnvelope:
        quote = entry.chunk_source_span.quote(document_text)
        return cls(
            source_document_version_id=source_document_version_id,
            chunking_policy_version=chunking_policy_version,
            chunk_id=entry.chunk_id,
            chunk_hash=entry.chunk_hash,
            chunk_source_span=entry.chunk_source_span,
            model_input=M1ModelInput(chunk_text=quote),
        )

    def model_payload(self) -> dict[str, str]:
        """Return the complete and only model-visible user payload."""
        return self.model_input.to_dict()

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "source_document_version_id": self.source_document_version_id,
            "chunking_policy_version": self.chunking_policy_version,
            "chunk_id": self.chunk_id,
            "chunk_hash": self.chunk_hash,
            "chunk_source_span": self.chunk_source_span.to_dict(),
            "model_input": self.model_input.to_dict(),
        }


@dataclass(frozen=True)
class M1CandidateMention:
    mention_type: str | None
    mention_scope: str | None
    mention_quote: str | None
    evidence_quotes: tuple[str, ...]

    @classmethod
    def parse(cls, value: Any, *, index: int) -> M1CandidateMention:
        if not isinstance(value, Mapping):
            raise ContractValidationError(f"candidate_mentions[{index}] must be an object")
        _expect_exact_keys(
            value,
            {"mention_type", "mention_scope", "mention_quote", "evidence_quotes"},
            label=f"candidate_mentions[{index}]",
        )
        mention_type = value["mention_type"]
        mention_scope = value["mention_scope"]
        mention_quote = value["mention_quote"]
        evidence_quotes = value["evidence_quotes"]
        if mention_type not in {"exact", "describe", None}:
            raise ContractValidationError(f"candidate_mentions[{index}].mention_type is invalid")
        if mention_scope not in {"individual", "collective", None}:
            raise ContractValidationError(f"candidate_mentions[{index}].mention_scope is invalid")
        if mention_type is None:
            if mention_quote is not None:
                raise ContractValidationError("null mention_type requires null mention_quote")
            if mention_scope is not None:
                raise ContractValidationError("null mention_type requires null mention_scope")
        elif not isinstance(mention_quote, str) or not mention_quote.strip():
            raise ContractValidationError("exact/describe mention requires a non-empty mention_quote")
        if mention_type == "exact" and mention_scope != "individual":
            raise ContractValidationError("exact mention_type requires individual mention_scope")
        if mention_type == "describe" and mention_scope not in {"individual", "collective"}:
            raise ContractValidationError("describe mention_type requires individual or collective mention_scope")
        if not isinstance(evidence_quotes, list) or not evidence_quotes:
            raise ContractValidationError("evidence_quotes must be a non-empty array")
        if any(not isinstance(quote, str) or not quote.strip() for quote in evidence_quotes):
            raise ContractValidationError("every evidence_quote must be a non-empty string")
        if len(set(evidence_quotes)) != len(evidence_quotes):
            raise ContractValidationError("evidence_quotes must be unique within a mention")
        return cls(mention_type, mention_scope, mention_quote, tuple(evidence_quotes))

    def to_dict(self) -> dict[str, object]:
        return {
            "mention_type": self.mention_type,
            "mention_scope": self.mention_scope,
            "mention_quote": self.mention_quote,
            "evidence_quotes": list(self.evidence_quotes),
        }


@dataclass(frozen=True)
class M1ModelOutput:
    candidate_mentions: tuple[M1CandidateMention, ...]

    @classmethod
    def parse(cls, raw: str | Mapping[str, Any]) -> M1ModelOutput:
        if isinstance(raw, str):
            try:
                value = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ContractValidationError("M1 provider returned invalid JSON") from exc
        else:
            value = raw
        if not isinstance(value, Mapping):
            raise ContractValidationError("M1 model output must be an object")
        _expect_exact_keys(value, {"candidate_mentions"}, label="M1 model output")
        candidates = value["candidate_mentions"]
        if not isinstance(candidates, list):
            raise ContractValidationError("candidate_mentions must be an array")
        return cls(tuple(M1CandidateMention.parse(item, index=index) for index, item in enumerate(candidates)))

    def to_dict(self) -> dict[str, object]:
        return {"candidate_mentions": [candidate.to_dict() for candidate in self.candidate_mentions]}


@dataclass(frozen=True)
class M1ProviderRequest:
    system_instruction: str
    user_payload: Mapping[str, Any]
    response_schema: Mapping[str, Any]
    response_schema_name: str = "m1_mention_discovery"


@runtime_checkable
class M1Provider(Protocol):
    def generate(self, request: M1ProviderRequest) -> str | Mapping[str, Any]: ...


@dataclass(frozen=True)
class M1BoundMention:
    local_mention_id: str
    candidate: M1CandidateMention


@dataclass(frozen=True)
class M1BoundResult:
    envelope: M1OrchestrationEnvelope
    model_output: M1ModelOutput
    mentions: tuple[M1BoundMention, ...]


class M1Orchestrator:
    """Build the minimal Provider request and bind validated output to its envelope."""

    def __init__(self, provider: M1Provider) -> None:
        self._provider = provider

    def run(self, envelope: M1OrchestrationEnvelope) -> M1BoundResult:
        request = M1ProviderRequest(
            system_instruction=M1_SYSTEM_INSTRUCTION,
            user_payload=copy.deepcopy(envelope.model_payload()),
            response_schema=copy.deepcopy(M1_RESPONSE_SCHEMA),
        )
        raw_output = self._provider.generate(request)
        model_output = M1ModelOutput.parse(raw_output)
        mentions = tuple(
            M1BoundMention(local_mention_id=f"m{index + 1}", candidate=candidate)
            for index, candidate in enumerate(model_output.candidate_mentions)
        )
        return M1BoundResult(envelope=envelope, model_output=model_output, mentions=mentions)
