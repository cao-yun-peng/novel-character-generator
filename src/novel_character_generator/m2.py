from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Iterable, Mapping, Protocol, runtime_checkable

from .errors import ContractValidationError
from .grounding import GroundedMention, GroundingResult
from .text import SourceSpan, find_safe_quote_matches, sha256_text

M2_ENVELOPE_VERSION = "m2-orchestration-envelope-v4"
M2_PROMOTION_ENVELOPE_VERSION = "m2-remaining-describe-promotion-envelope-v4"
M2_PROMOTED_RESULT_VERSION = "grounded-promoted-describe-characters-v6"
M2_PROMOTION_GROUNDING_POLICY_VERSION = "promotion-partial-fact-acceptance-v1"
M2_CONTEXT_VERSION = "m2-full-chunk-context-v1"
M2_RESOLVER_VERSION = "m2-minimal-fact-binding-v1"
M2_ATTRIBUTION_GROUNDING_POLICY_VERSION = "unique-fact-occurrence-attribution-v2"

M2_CATEGORIES = (
    "age",
    "body",
    "face",
    "hair",
    "clothing",
    "accessory",
    "distinctive_mark",
    "appearance_state",
    "other_visual",
)

M2_ATTRIBUTION_SYSTEM_INSTRUCTION = """
你负责判断允许证据中的哪些可见外貌事实明确属于当前 target 人物。

严格遵守以下规则：

1. 只使用 user payload 中 target.approved_evidence_quotes 和 describe_blocks[].evidence_quotes 作为事实来源；chunk_text 只用于理解局部指代和人物关系。
2. 只输出肯定属于当前 target 的、原文明示的当前视觉事实。否定、不确定、猜测、比喻推断、心理、性格、身份、能力、动作和背景信息全部省略。
3. fact_quote 必须是允许证据中的最小、连续原文片段，逐字复制，不改写、不概括、不补写。不要只从 chunk_text 的其他位置取词。
4. category 只能是 age、body、face、hair、clothing、accessory、distinctive_mark、appearance_state、other_visual。
5. attribute 和 value 用简短中文表达事实结构，但不得改变 fact_quote。
6. 没有符合条件的事实时返回空 belongs_to_target 数组。
7. 只输出 response schema 允许的 JSON，不输出解释、引用编号、span、状态、hash 或其他系统字段。
"""

M2_PROMOTION_SYSTEM_INSTRUCTION = """
你负责把一个尚未归属的 describe 外貌证据池解析为一个或多个 Chunk 内人物。

严格遵守以下规则：

1. 事实只能来自 describe.remaining_evidence_quotes；chunk_text 只用于理解局部人物关系。
2. character_label_quote 优先逐字复制 describe.mention_quote；也可逐字来自剩余证据并能指向该人物。fact_quote 必须是剩余证据中的最小连续原文片段。
3. 只输出原文明示、肯定属于相应人物的当前可见外貌事实。否定、不确定、推断及非外貌信息全部省略。
4. 一个证据池确实包含多个人物时可以输出多个人物；不得把群体描述合并成一个人物。
5. category 只能是 age、body、face、hair、clothing、accessory、distinctive_mark、appearance_state、other_visual。
6. 只输出 response schema 允许的 JSON，不输出 ref、span、状态、hash、审计字段或解释。
"""

M2_MODEL_FACT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["fact_quote", "category", "attribute", "value"],
    "properties": {
        "fact_quote": {"type": "string", "minLength": 1},
        "category": {"type": "string", "enum": list(M2_CATEGORIES)},
        "attribute": {"type": "string", "minLength": 1},
        "value": {"type": "string", "minLength": 1},
    },
}

M2_ATTRIBUTION_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["belongs_to_target"],
    "properties": {
        "belongs_to_target": {
            "type": "array",
            "items": copy.deepcopy(M2_MODEL_FACT_SCHEMA),
        }
    },
}

M2_PROMOTION_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["characters"],
    "properties": {
        "characters": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["character_label_quote", "belongs_to_character"],
                "properties": {
                    "character_label_quote": {"type": "string", "minLength": 1},
                    "belongs_to_character": {
                        "type": "array",
                        "minItems": 1,
                        "items": copy.deepcopy(M2_MODEL_FACT_SCHEMA),
                    },
                },
            },
        }
    },
}


def _canonical_hash(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(payload.encode("utf-8")).hexdigest()


def _expect_exact_keys(value: Mapping[str, Any], keys: set[str], *, label: str) -> None:
    actual = set(value)
    if actual != keys:
        raise ContractValidationError(
            f"{label} fields mismatch; missing={sorted(keys - actual)}, extra={sorted(actual - keys)}"
        )


def _non_empty_string(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractValidationError(f"{label} must be a non-empty string")
    return value


def _unique_in_order(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)


@dataclass(frozen=True)
class M2ProviderRequest:
    system_instruction: str
    user_payload: Mapping[str, Any]
    response_schema: Mapping[str, Any]
    response_schema_name: str


@runtime_checkable
class M2Provider(Protocol):
    def generate(self, request: M2ProviderRequest) -> str | Mapping[str, Any]: ...


@dataclass(frozen=True)
class LocalCharacterRef:
    source_document_version_id: str
    chunk_id: str
    local_mention_id: str
    packet_hash: str
    mention_type: str = "exact"

    def __post_init__(self) -> None:
        for label, value in (
            ("source_document_version_id", self.source_document_version_id),
            ("chunk_id", self.chunk_id),
            ("local_mention_id", self.local_mention_id),
            ("packet_hash", self.packet_hash),
        ):
            _non_empty_string(value, label=label)
        if self.mention_type != "exact":
            raise ContractValidationError("LocalCharacterRef mention_type must be exact")
        if not _is_sha256(self.packet_hash):
            raise ContractValidationError("LocalCharacterRef packet_hash must be lowercase SHA-256")

    def to_dict(self) -> dict[str, str]:
        return {
            "source_document_version_id": self.source_document_version_id,
            "chunk_id": self.chunk_id,
            "local_mention_id": self.local_mention_id,
            "mention_type": self.mention_type,
            "packet_hash": self.packet_hash,
        }


@dataclass(frozen=True)
class M2ModelFact:
    fact_quote: str
    category: str
    attribute: str
    value: str

    @classmethod
    def parse(cls, value: Any, *, label: str) -> M2ModelFact:
        if not isinstance(value, Mapping):
            raise ContractValidationError(f"{label} must be an object")
        _expect_exact_keys(value, {"fact_quote", "category", "attribute", "value"}, label=label)
        fact_quote = _non_empty_string(value["fact_quote"], label=f"{label}.fact_quote")
        category = _non_empty_string(value["category"], label=f"{label}.category")
        if category not in M2_CATEGORIES:
            raise ContractValidationError(f"{label}.category is invalid")
        return cls(
            fact_quote=fact_quote,
            category=category,
            attribute=_non_empty_string(value["attribute"], label=f"{label}.attribute"),
            value=_non_empty_string(value["value"], label=f"{label}.value"),
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "fact_quote": self.fact_quote,
            "category": self.category,
            "attribute": self.attribute,
            "value": self.value,
        }


@dataclass(frozen=True)
class M2TargetModelInput:
    mention_quote: str
    approved_evidence_quotes: tuple[str, ...]

    def __post_init__(self) -> None:
        _non_empty_string(self.mention_quote, label="target.mention_quote")
        if not self.approved_evidence_quotes:
            raise ContractValidationError("target.approved_evidence_quotes must not be empty")

    def to_dict(self) -> dict[str, object]:
        return {
            "mention_quote": self.mention_quote,
            "approved_evidence_quotes": list(self.approved_evidence_quotes),
        }


@dataclass(frozen=True)
class M2DescribeModelInput:
    mention_quote: str
    evidence_quotes: tuple[str, ...]

    def __post_init__(self) -> None:
        _non_empty_string(self.mention_quote, label="describe.mention_quote")
        if not self.evidence_quotes:
            raise ContractValidationError("describe.evidence_quotes must not be empty")

    def to_dict(self) -> dict[str, object]:
        return {"mention_quote": self.mention_quote, "evidence_quotes": list(self.evidence_quotes)}


@dataclass(frozen=True)
class M2AttributionModelInput:
    target: M2TargetModelInput
    describe_blocks: tuple[M2DescribeModelInput, ...]
    chunk_text: str

    def __post_init__(self) -> None:
        _non_empty_string(self.chunk_text, label="chunk_text")

    def to_dict(self) -> dict[str, object]:
        return {
            "target": self.target.to_dict(),
            "describe_blocks": [item.to_dict() for item in self.describe_blocks],
            "chunk_text": self.chunk_text,
        }


@dataclass(frozen=True)
class M2AttributionModelOutput:
    belongs_to_target: tuple[M2ModelFact, ...]

    @classmethod
    def parse(cls, raw: str | Mapping[str, Any]) -> M2AttributionModelOutput:
        value = _parse_json_object(raw, label="M2 attribution model output")
        _expect_exact_keys(value, {"belongs_to_target"}, label="M2 attribution model output")
        facts = value["belongs_to_target"]
        if not isinstance(facts, list):
            raise ContractValidationError("belongs_to_target must be an array")
        return cls(tuple(M2ModelFact.parse(item, label=f"belongs_to_target[{i}]") for i, item in enumerate(facts)))

    def to_dict(self) -> dict[str, object]:
        return {"belongs_to_target": [fact.to_dict() for fact in self.belongs_to_target]}


def _parse_json_object(raw: str | Mapping[str, Any], *, label: str) -> Mapping[str, Any]:
    if isinstance(raw, str):
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ContractValidationError(f"{label} is invalid JSON") from exc
    else:
        value = raw
    if not isinstance(value, Mapping):
        raise ContractValidationError(f"{label} must be an object")
    return value


@dataclass(frozen=True)
class M2EvidenceBinding:
    evidence_ref: str
    source_evidence_quote: str
    source_evidence_span: SourceSpan

    def to_dict(self) -> dict[str, object]:
        return {
            "evidence_ref": self.evidence_ref,
            "source_evidence_quote": self.source_evidence_quote,
            "source_evidence_span": self.source_evidence_span.to_dict(),
        }


@dataclass(frozen=True)
class M2DescribeFragmentBinding:
    fragment_ref: str
    source_evidence_quote: str
    source_evidence_span: SourceSpan
    fragment_quote: str
    fragment_span: SourceSpan

    def to_dict(self) -> dict[str, object]:
        return {
            "fragment_ref": self.fragment_ref,
            "source_evidence_quote": self.source_evidence_quote,
            "source_evidence_span": self.source_evidence_span.to_dict(),
            "fragment_quote": self.fragment_quote,
            "fragment_span": self.fragment_span.to_dict(),
        }


@dataclass(frozen=True)
class M2DescribeSourceBinding:
    describe_ref: str
    local_mention_id: str
    mention_quote: str
    packet_hash: str
    available_evidence_fragments: tuple[M2DescribeFragmentBinding, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "describe_ref": self.describe_ref,
            "local_mention_id": self.local_mention_id,
            "mention_quote": self.mention_quote,
            "packet_hash": self.packet_hash,
            "available_evidence_fragments": [item.to_dict() for item in self.available_evidence_fragments],
        }


def _validate_grounding_chunk(grounding: GroundingResult, chunk_text: str) -> None:
    _non_empty_string(chunk_text, label="chunk_text")
    if grounding.chunk_hash != sha256_text(chunk_text):
        raise ContractValidationError("chunk_text hash does not match GroundingResult")
    if grounding.chunk_source_span.end - grounding.chunk_source_span.start != len(chunk_text):
        raise ContractValidationError("chunk_text length does not match GroundingResult span")


def _evidence_occurrences(mention: GroundedMention, chunk_text: str) -> tuple[tuple[str, SourceSpan], ...]:
    occurrences: list[tuple[str, SourceSpan]] = []
    for evidence in mention.approved_evidence:
        for span in evidence.source_spans:
            if span.quote(chunk_text) != evidence.evidence_quote:
                raise ContractValidationError("grounded evidence span no longer matches chunk_text")
            occurrences.append((evidence.evidence_quote, span))
    return tuple(sorted(occurrences, key=lambda item: (item[1].start, item[1].end, item[0])))


@dataclass(frozen=True)
class M2OrchestrationEnvelope:
    target_character_ref: LocalCharacterRef
    target_evidence_bindings: tuple[M2EvidenceBinding, ...]
    describe_source_bindings: tuple[M2DescribeSourceBinding, ...]
    context_version: str
    resolver_version: str
    resolution_round: int
    task_cache_key: str
    model_input: M2AttributionModelInput
    schema_version: str = M2_ENVELOPE_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != M2_ENVELOPE_VERSION:
            raise ContractValidationError("unsupported M2 envelope schema_version")
        _non_empty_string(self.context_version, label="context_version")
        _non_empty_string(self.resolver_version, label="resolver_version")
        if self.resolution_round < 1:
            raise ContractValidationError("resolution_round must be at least one")
        if not _is_sha256(self.task_cache_key):
            raise ContractValidationError("task_cache_key must be lowercase SHA-256")
        if not self.target_evidence_bindings:
            raise ContractValidationError("target_evidence_bindings must not be empty")
        target_quotes = _unique_in_order(item.source_evidence_quote for item in self.target_evidence_bindings)
        if target_quotes != self.model_input.target.approved_evidence_quotes:
            raise ContractValidationError("model target evidence does not match code bindings")
        if len(self.describe_source_bindings) != len(self.model_input.describe_blocks):
            raise ContractValidationError("model describe blocks do not match code bindings")
        for source, model_block in zip(self.describe_source_bindings, self.model_input.describe_blocks):
            if source.mention_quote != model_block.mention_quote:
                raise ContractValidationError("model describe mention does not match code binding")
            quotes = _unique_in_order(item.fragment_quote for item in source.available_evidence_fragments)
            if quotes != model_block.evidence_quotes:
                raise ContractValidationError("model describe evidence does not match code bindings")

    @classmethod
    def from_grounding(
        cls,
        grounding: GroundingResult,
        *,
        chunk_text: str,
        target_local_mention_id: str,
        context_version: str = M2_CONTEXT_VERSION,
        resolver_version: str = M2_RESOLVER_VERSION,
        resolution_round: int = 1,
    ) -> M2OrchestrationEnvelope:
        _validate_grounding_chunk(grounding, chunk_text)
        if resolution_round < 1:
            raise ContractValidationError("resolution_round must be at least one")
        target = next(
            (item for item in grounding.single_character_mentions if item.local_mention_id == target_local_mention_id),
            None,
        )
        if target is None or target.mention_type != "exact" or target.mention_quote is None:
            raise ContractValidationError("M2 target must be an individual exact grounded mention")

        target_occurrences = _evidence_occurrences(target, chunk_text)
        if not target_occurrences:
            raise ContractValidationError("M2 target must have approved evidence")
        target_bindings = tuple(
            M2EvidenceBinding(f"t{i}", quote, span)
            for i, (quote, span) in enumerate(target_occurrences, start=1)
        )

        describe_mentions = tuple(
            item
            for item in grounding.single_character_mentions
            if item.mention_type == "describe" and item.mention_quote is not None
        )
        describe_bindings: list[M2DescribeSourceBinding] = []
        describe_inputs: list[M2DescribeModelInput] = []
        for describe_index, mention in enumerate(describe_mentions, start=1):
            occurrences = _evidence_occurrences(mention, chunk_text)
            if not occurrences:
                continue
            describe_ref = f"d{describe_index}"
            fragments = tuple(
                M2DescribeFragmentBinding(
                    fragment_ref=f"{describe_ref}-f{fragment_index}",
                    source_evidence_quote=quote,
                    source_evidence_span=span,
                    fragment_quote=quote,
                    fragment_span=span,
                )
                for fragment_index, (quote, span) in enumerate(occurrences, start=1)
            )
            describe_bindings.append(
                M2DescribeSourceBinding(
                    describe_ref=describe_ref,
                    local_mention_id=mention.local_mention_id,
                    mention_quote=mention.mention_quote,
                    packet_hash=mention.packet_hash,
                    available_evidence_fragments=fragments,
                )
            )
            describe_inputs.append(
                M2DescribeModelInput(
                    mention_quote=mention.mention_quote,
                    evidence_quotes=_unique_in_order(fragment.fragment_quote for fragment in fragments),
                )
            )

        model_input = M2AttributionModelInput(
            target=M2TargetModelInput(
                mention_quote=target.mention_quote,
                approved_evidence_quotes=_unique_in_order(quote for quote, _ in target_occurrences),
            ),
            describe_blocks=tuple(describe_inputs),
            chunk_text=chunk_text,
        )
        target_ref = LocalCharacterRef(
            source_document_version_id=grounding.source_document_version_id,
            chunk_id=grounding.chunk_id,
            local_mention_id=target.local_mention_id,
            packet_hash=target.packet_hash,
        )
        ordered_describe_pool_hash = _canonical_hash(
            [binding.to_dict() for binding in describe_bindings]
        )
        cache_key = _canonical_hash(
            {
                "target_packet_hash": target.packet_hash,
                "ordered_describe_pool_hash": ordered_describe_pool_hash,
                "context_version": context_version,
                "resolver_version": resolver_version,
            }
        )
        return cls(
            target_character_ref=target_ref,
            target_evidence_bindings=target_bindings,
            describe_source_bindings=tuple(describe_bindings),
            context_version=context_version,
            resolver_version=resolver_version,
            resolution_round=resolution_round,
            task_cache_key=cache_key,
            model_input=model_input,
        )

    def model_payload(self) -> dict[str, object]:
        return self.model_input.to_dict()

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "target_character_ref": self.target_character_ref.to_dict(),
            "target_evidence_bindings": [item.to_dict() for item in self.target_evidence_bindings],
            "describe_source_bindings": [item.to_dict() for item in self.describe_source_bindings],
            "context_version": self.context_version,
            "resolver_version": self.resolver_version,
            "resolution_round": self.resolution_round,
            "task_cache_key": self.task_cache_key,
            "model_input": self.model_input.to_dict(),
        }


def build_m2_attribution_envelopes(
    grounding: GroundingResult,
    *,
    chunk_text: str,
    context_version: str = M2_CONTEXT_VERSION,
    resolver_version: str = M2_RESOLVER_VERSION,
    resolution_round: int = 1,
) -> tuple[M2OrchestrationEnvelope, ...]:
    return tuple(
        M2OrchestrationEnvelope.from_grounding(
            grounding,
            chunk_text=chunk_text,
            target_local_mention_id=mention.local_mention_id,
            context_version=context_version,
            resolver_version=resolver_version,
            resolution_round=resolution_round,
        )
        for mention in grounding.single_character_mentions
        if mention.mention_type == "exact"
    )


@dataclass(frozen=True)
class M2GroundingIssue:
    code: str
    fact_index: int | None
    detail: str
    character_index: int | None = None
    fact_quote: str | None = None
    candidate_occurrence_count: int | None = None
    candidate_occurrences: tuple[Mapping[str, object], ...] = ()

    def to_dict(self) -> dict[str, object]:
        value: dict[str, object] = {
            "code": self.code,
            "fact_index": self.fact_index,
            "detail": self.detail,
        }
        if self.character_index is not None:
            value["character_index"] = self.character_index
        if self.fact_quote is not None:
            value["fact_quote"] = self.fact_quote
        if self.candidate_occurrence_count is not None:
            value["candidate_occurrence_count"] = self.candidate_occurrence_count
        if self.candidate_occurrences:
            value["candidate_occurrences"] = [dict(item) for item in self.candidate_occurrences]
        return value


@dataclass(frozen=True)
class M2GroundedFact:
    fact_quote: str
    category: str
    attribute: str
    value: str
    source_mention_id: str
    source_mention_type: str
    source_evidence_quote: str
    source_evidence_span: SourceSpan
    fact_chunk_span: SourceSpan
    match_mode: str

    def to_dict(self) -> dict[str, object]:
        return {
            "fact_quote": self.fact_quote,
            "category": self.category,
            "attribute": self.attribute,
            "value": self.value,
            "source_mention_id": self.source_mention_id,
            "source_mention_type": self.source_mention_type,
            "source_evidence_quote": self.source_evidence_quote,
            "source_evidence_span": self.source_evidence_span.to_dict(),
            "fact_chunk_span": self.fact_chunk_span.to_dict(),
            "match_mode": self.match_mode,
        }


@dataclass(frozen=True)
class _FactBindingCandidate:
    source_mention_id: str
    source_mention_type: str
    source_evidence_quote: str
    source_evidence_span: SourceSpan
    raw_fact_quote: str
    fact_chunk_span: SourceSpan
    match_mode: str


def _fact_candidates(
    fact_quote: str,
    bindings: Iterable[tuple[str, str, str, SourceSpan, str, SourceSpan]],
) -> tuple[_FactBindingCandidate, ...]:
    candidates: list[_FactBindingCandidate] = []
    for mention_id, mention_type, evidence_quote, evidence_span, search_quote, search_span in bindings:
        for match in find_safe_quote_matches(search_quote, fact_quote):
            candidates.append(
                _FactBindingCandidate(
                    source_mention_id=mention_id,
                    source_mention_type=mention_type,
                    source_evidence_quote=evidence_quote,
                    source_evidence_span=evidence_span,
                    raw_fact_quote=match.raw_quote,
                    fact_chunk_span=SourceSpan(
                        search_span.start + match.span.start,
                        search_span.start + match.span.end,
                    ),
                    match_mode=match.match_mode,
                )
            )
    exact = tuple(item for item in candidates if item.match_mode == "exact")
    selected = exact if exact else tuple(candidates)
    return tuple(
        sorted(
            selected,
            key=lambda item: (
                item.fact_chunk_span.start,
                item.fact_chunk_span.end,
                item.source_mention_id,
            ),
        )
    )


@dataclass(frozen=True)
class M2GroundedAttributionResult:
    target_character_ref: LocalCharacterRef
    task_cache_key: str
    grounded_belongs_to_target: tuple[M2GroundedFact, ...]
    issues: tuple[M2GroundingIssue, ...]

    def to_packet_dict(self) -> dict[str, object]:
        return {
            "grounding_policy_version": M2_ATTRIBUTION_GROUNDING_POLICY_VERSION,
            "target_character_ref": self.target_character_ref.to_dict(),
            "task_cache_key": self.task_cache_key,
            "grounded_belongs_to_target": [fact.to_dict() for fact in self.grounded_belongs_to_target],
        }

    def to_audit_dict(self) -> dict[str, object]:
        value = self.to_packet_dict()
        value["issues"] = [issue.to_dict() for issue in self.issues]
        return value


def _unique_attribution_occurrences(
    candidates: tuple[_FactBindingCandidate, ...],
) -> tuple[_FactBindingCandidate, ...]:
    """Multiple evidence windows may support the same occurrence for one owner."""
    unique: dict[tuple[str, SourceSpan], _FactBindingCandidate] = {}
    for candidate in sorted(candidates, key=lambda item: (
        item.fact_chunk_span.start, item.fact_chunk_span.end, item.source_mention_id,
        item.source_evidence_span.start, item.source_evidence_span.end,
    )):
        unique.setdefault((candidate.source_mention_id, candidate.fact_chunk_span), candidate)
    return tuple(unique.values())


def _ambiguous_attribution_issue(
    fact_index: int, fact_quote: str, candidates: tuple[_FactBindingCandidate, ...],
) -> M2GroundingIssue:
    return M2GroundingIssue(
        "ambiguous_fact_binding", fact_index,
        "fact matched multiple allowed occurrences; no occurrence selected",
        fact_quote=fact_quote,
        candidate_occurrence_count=len(candidates),
        candidate_occurrences=tuple({
            "source_mention_id": item.source_mention_id,
            "source_mention_type": item.source_mention_type,
            "source_evidence_span": item.source_evidence_span.to_dict(),
            "fact_chunk_span": item.fact_chunk_span.to_dict(),
        } for item in candidates),
    )


def ground_m2_attribution_output(
    envelope: M2OrchestrationEnvelope,
    output: M2AttributionModelOutput,
) -> M2GroundedAttributionResult:
    target_bindings = tuple(
        (
            envelope.target_character_ref.local_mention_id,
            "exact",
            item.source_evidence_quote,
            item.source_evidence_span,
            item.source_evidence_quote,
            item.source_evidence_span,
        )
        for item in envelope.target_evidence_bindings
    )
    describe_bindings = tuple(
        (
            source.local_mention_id,
            "describe",
            fragment.source_evidence_quote,
            fragment.source_evidence_span,
            fragment.fragment_quote,
            fragment.fragment_span,
        )
        for source in envelope.describe_source_bindings
        for fragment in source.available_evidence_fragments
    )
    grounded: list[M2GroundedFact] = []
    issues: list[M2GroundingIssue] = []
    seen: set[tuple[object, ...]] = set()

    for fact_index, fact in enumerate(output.belongs_to_target):
        target_candidates = _unique_attribution_occurrences(_fact_candidates(fact.fact_quote, target_bindings))
        candidate: _FactBindingCandidate | None = None
        if target_candidates:
            if len(target_candidates) == 1:
                candidate = target_candidates[0]
            else:
                issues.append(_ambiguous_attribution_issue(fact_index, fact.fact_quote, target_candidates))
        else:
            describe_candidates = _unique_attribution_occurrences(_fact_candidates(fact.fact_quote, describe_bindings))
            if len(describe_candidates) == 1:
                candidate = describe_candidates[0]
            elif len(describe_candidates) > 1:
                issues.append(_ambiguous_attribution_issue(fact_index, fact.fact_quote, describe_candidates))
            else:
                issues.append(
                    M2GroundingIssue(
                        "fact_not_in_allowed_evidence",
                        fact_index,
                        "fact_quote did not safely match target or describe evidence",
                    )
                )
        if candidate is None:
            continue
        hydrated = M2GroundedFact(
            fact_quote=candidate.raw_fact_quote,
            category=fact.category,
            attribute=fact.attribute,
            value=fact.value,
            source_mention_id=candidate.source_mention_id,
            source_mention_type=candidate.source_mention_type,
            source_evidence_quote=candidate.source_evidence_quote,
            source_evidence_span=candidate.source_evidence_span,
            fact_chunk_span=candidate.fact_chunk_span,
            match_mode=candidate.match_mode,
        )
        identity = (
            hydrated.fact_chunk_span,
            hydrated.category,
            hydrated.attribute,
            hydrated.value,
            hydrated.source_mention_id,
        )
        if identity in seen:
            issues.append(M2GroundingIssue("duplicate_model_fact", fact_index, "duplicate grounded fact omitted"))
            continue
        seen.add(identity)
        grounded.append(hydrated)

    return M2GroundedAttributionResult(
        target_character_ref=envelope.target_character_ref,
        task_cache_key=envelope.task_cache_key,
        grounded_belongs_to_target=tuple(grounded),
        issues=tuple(issues),
    )


class M2AttributionOrchestrator:
    def __init__(self, provider: M2Provider) -> None:
        self._provider = provider

    def run(self, envelope: M2OrchestrationEnvelope) -> M2GroundedAttributionResult:
        request = M2ProviderRequest(
            system_instruction=M2_ATTRIBUTION_SYSTEM_INSTRUCTION,
            user_payload=copy.deepcopy(envelope.model_payload()),
            response_schema=copy.deepcopy(M2_ATTRIBUTION_RESPONSE_SCHEMA),
            response_schema_name="m2_target_appearance_facts",
        )
        output = M2AttributionModelOutput.parse(self._provider.generate(request))
        return ground_m2_attribution_output(envelope, output)


@dataclass(frozen=True)
class RemainingEvidenceFragment:
    fragment_ref: str
    source_evidence_quote: str
    source_evidence_span: SourceSpan
    fragment_quote: str
    fragment_span: SourceSpan

    def __post_init__(self) -> None:
        _non_empty_string(self.fragment_ref, label="fragment_ref")
        _non_empty_string(self.source_evidence_quote, label="source_evidence_quote")
        _non_empty_string(self.fragment_quote, label="fragment_quote")
        if not (
            self.source_evidence_span.start <= self.fragment_span.start
            and self.fragment_span.end <= self.source_evidence_span.end
        ):
            raise ContractValidationError("fragment_span must be contained in source_evidence_span")

    def to_dict(self) -> dict[str, object]:
        return {
            "fragment_ref": self.fragment_ref,
            "source_evidence_quote": self.source_evidence_quote,
            "source_evidence_span": self.source_evidence_span.to_dict(),
            "fragment_quote": self.fragment_quote,
            "fragment_span": self.fragment_span.to_dict(),
        }


@dataclass(frozen=True)
class DescribeEvidenceRef:
    local_mention_id: str
    packet_hash: str

    def __post_init__(self) -> None:
        _non_empty_string(self.local_mention_id, label="local_mention_id")
        if not _is_sha256(self.packet_hash):
            raise ContractValidationError("DescribeEvidenceRef packet_hash must be lowercase SHA-256")

    def to_dict(self) -> dict[str, str]:
        return {"local_mention_id": self.local_mention_id, "packet_hash": self.packet_hash}


@dataclass(frozen=True)
class M2PromotionModelInput:
    mention_quote: str
    remaining_evidence_quotes: tuple[str, ...]
    chunk_text: str

    def __post_init__(self) -> None:
        _non_empty_string(self.mention_quote, label="describe.mention_quote")
        if not self.remaining_evidence_quotes:
            raise ContractValidationError("remaining_evidence_quotes must not be empty")
        if any(not isinstance(item, str) or not item for item in self.remaining_evidence_quotes):
            raise ContractValidationError("remaining_evidence_quotes must contain non-empty strings")
        _non_empty_string(self.chunk_text, label="chunk_text")

    def to_dict(self) -> dict[str, object]:
        return {
            "describe": {
                "mention_quote": self.mention_quote,
                "remaining_evidence_quotes": list(self.remaining_evidence_quotes),
            },
            "chunk_text": self.chunk_text,
        }


@dataclass(frozen=True)
class M2PromotionEnvelope:
    source_document_version_id: str
    chunk_id: str
    describe_source_ref: DescribeEvidenceRef
    remaining_fragment_bindings: tuple[RemainingEvidenceFragment, ...]
    context_version: str
    resolver_version: str
    pool_hash: str
    promotion_hash: str
    model_input: M2PromotionModelInput
    schema_version: str = M2_PROMOTION_ENVELOPE_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != M2_PROMOTION_ENVELOPE_VERSION:
            raise ContractValidationError("unsupported M2 promotion envelope schema_version")
        _non_empty_string(self.source_document_version_id, label="source_document_version_id")
        _non_empty_string(self.chunk_id, label="chunk_id")
        _non_empty_string(self.context_version, label="context_version")
        _non_empty_string(self.resolver_version, label="resolver_version")
        if not _is_sha256(self.pool_hash) or not _is_sha256(self.promotion_hash):
            raise ContractValidationError("pool_hash and promotion_hash must be lowercase SHA-256")
        if not self.remaining_fragment_bindings:
            raise ContractValidationError("remaining_fragment_bindings must not be empty")
        quotes = _unique_in_order(item.fragment_quote for item in self.remaining_fragment_bindings)
        if quotes != self.model_input.remaining_evidence_quotes:
            raise ContractValidationError("promotion model evidence does not match code bindings")

    @classmethod
    def from_grounded_describe(
        cls,
        grounding: GroundingResult,
        *,
        chunk_text: str,
        describe_local_mention_id: str,
        remaining_fragments: Iterable[RemainingEvidenceFragment] | None = None,
        pool_hash_override: str | None = None,
        context_version: str = M2_CONTEXT_VERSION,
        resolver_version: str = M2_RESOLVER_VERSION,
    ) -> M2PromotionEnvelope:
        _validate_grounding_chunk(grounding, chunk_text)
        mention = next(
            (item for item in grounding.single_character_mentions if item.local_mention_id == describe_local_mention_id),
            None,
        )
        if mention is None or mention.mention_type != "describe" or mention.mention_quote is None:
            raise ContractValidationError("promotion source must be an individual describe mention")
        if remaining_fragments is None:
            occurrences = _evidence_occurrences(mention, chunk_text)
            fragments = tuple(
                RemainingEvidenceFragment(
                    fragment_ref=f"d1-f{i}",
                    source_evidence_quote=quote,
                    source_evidence_span=span,
                    fragment_quote=quote,
                    fragment_span=span,
                )
                for i, (quote, span) in enumerate(occurrences, start=1)
            )
        else:
            fragments = tuple(remaining_fragments)
        if not fragments:
            raise ContractValidationError("promotion requires at least one remaining fragment")
        fragments = tuple(sorted(fragments, key=lambda item: (item.fragment_span.start, item.fragment_span.end)))
        for fragment in fragments:
            if fragment.source_evidence_span.quote(chunk_text) != fragment.source_evidence_quote:
                raise ContractValidationError("source evidence span does not match chunk_text")
            if fragment.fragment_span.quote(chunk_text) != fragment.fragment_quote:
                raise ContractValidationError("remaining fragment span does not match chunk_text")
            if not (
                fragment.source_evidence_span.start <= fragment.fragment_span.start
                and fragment.fragment_span.end <= fragment.source_evidence_span.end
            ):
                raise ContractValidationError("remaining fragment is outside source evidence")

        pool_hash = pool_hash_override or _canonical_hash([item.to_dict() for item in fragments])
        if not _is_sha256(pool_hash):
            raise ContractValidationError("pool_hash_override must be lowercase SHA-256")
        promotion_hash = _canonical_hash(
            {
                "source_document_version_id": grounding.source_document_version_id,
                "chunk_id": grounding.chunk_id,
                "describe_packet_hash": mention.packet_hash,
                "pool_hash": pool_hash,
                "context_version": context_version,
                "resolver_version": resolver_version,
            }
        )
        return cls(
            source_document_version_id=grounding.source_document_version_id,
            chunk_id=grounding.chunk_id,
            describe_source_ref=DescribeEvidenceRef(mention.local_mention_id, mention.packet_hash),
            remaining_fragment_bindings=fragments,
            context_version=context_version,
            resolver_version=resolver_version,
            pool_hash=pool_hash,
            promotion_hash=promotion_hash,
            model_input=M2PromotionModelInput(
                mention_quote=mention.mention_quote,
                remaining_evidence_quotes=_unique_in_order(item.fragment_quote for item in fragments),
                chunk_text=chunk_text,
            ),
        )

    def model_payload(self) -> dict[str, object]:
        return self.model_input.to_dict()

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "source_document_version_id": self.source_document_version_id,
            "chunk_id": self.chunk_id,
            "describe_source_ref": self.describe_source_ref.to_dict(),
            "remaining_fragment_bindings": [item.to_dict() for item in self.remaining_fragment_bindings],
            "context_version": self.context_version,
            "resolver_version": self.resolver_version,
            "pool_hash": self.pool_hash,
            "promotion_hash": self.promotion_hash,
            "model_input": self.model_input.to_dict(),
        }


@dataclass(frozen=True)
class M2PromotionCharacterOutput:
    character_label_quote: str
    belongs_to_character: tuple[M2ModelFact, ...]


@dataclass(frozen=True)
class M2PromotionModelOutput:
    characters: tuple[M2PromotionCharacterOutput, ...]

    @classmethod
    def parse(cls, raw: str | Mapping[str, Any]) -> M2PromotionModelOutput:
        value = _parse_json_object(raw, label="M2 promotion model output")
        _expect_exact_keys(value, {"characters"}, label="M2 promotion model output")
        characters = value["characters"]
        if not isinstance(characters, list) or not characters:
            raise ContractValidationError("characters must be a non-empty array")
        parsed: list[M2PromotionCharacterOutput] = []
        for index, item in enumerate(characters):
            label = f"characters[{index}]"
            if not isinstance(item, Mapping):
                raise ContractValidationError(f"{label} must be an object")
            _expect_exact_keys(item, {"character_label_quote", "belongs_to_character"}, label=label)
            facts = item["belongs_to_character"]
            if not isinstance(facts, list) or not facts:
                raise ContractValidationError(f"{label}.belongs_to_character must be a non-empty array")
            parsed.append(
                M2PromotionCharacterOutput(
                    character_label_quote=_non_empty_string(
                        item["character_label_quote"], label=f"{label}.character_label_quote"
                    ),
                    belongs_to_character=tuple(
                        M2ModelFact.parse(fact, label=f"{label}.belongs_to_character[{fact_index}]")
                        for fact_index, fact in enumerate(facts)
                    ),
                )
            )
        return cls(tuple(parsed))


@dataclass(frozen=True)
class PromotedDescribeCharacterRef:
    source_document_version_id: str
    chunk_id: str
    source_local_mention_id: str
    promotion_index: int
    packet_hash: str
    promotion_hash: str
    source_mention_type: str = "describe"
    character_origin: str = "remaining_describe"

    def to_dict(self) -> dict[str, object]:
        return {
            "source_document_version_id": self.source_document_version_id,
            "chunk_id": self.chunk_id,
            "source_local_mention_id": self.source_local_mention_id,
            "source_mention_type": self.source_mention_type,
            "promotion_index": self.promotion_index,
            "character_origin": self.character_origin,
            "packet_hash": self.packet_hash,
            "promotion_hash": self.promotion_hash,
        }


@dataclass(frozen=True)
class M2GroundedPromotedCharacter:
    promoted_character_ref: PromotedDescribeCharacterRef
    character_label_quote: str
    grounded_belongs_to_character: tuple[M2GroundedFact, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "promoted_character_ref": self.promoted_character_ref.to_dict(),
            "character_label_quote": self.character_label_quote,
            "grounded_belongs_to_character": [fact.to_dict() for fact in self.grounded_belongs_to_character],
        }


@dataclass(frozen=True)
class M2GroundedPromotionResult:
    describe_source_ref: DescribeEvidenceRef
    promotion_hash: str
    promoted_characters: tuple[M2GroundedPromotedCharacter, ...]
    unassigned_fragments: tuple[RemainingEvidenceFragment, ...]
    issues: tuple[M2GroundingIssue, ...]
    schema_version: str = M2_PROMOTED_RESULT_VERSION
    grounding_policy_version: str = M2_PROMOTION_GROUNDING_POLICY_VERSION

    @property
    def promotion_review_required(self) -> bool:
        return bool(self.issues)

    def to_packet_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "grounding_policy_version": self.grounding_policy_version,
            "describe_source_ref": self.describe_source_ref.to_dict(),
            "promotion_hash": self.promotion_hash,
            "promoted_characters": [item.to_dict() for item in self.promoted_characters],
            "unassigned_fragments": [item.to_dict() for item in self.unassigned_fragments],
        }

    def to_audit_dict(self) -> dict[str, object]:
        value = self.to_packet_dict()
        value["promotion_review_required"] = self.promotion_review_required
        value["issues"] = [issue.to_dict() for issue in self.issues]
        return value


@dataclass(frozen=True)
class _ProvisionalPromotedCharacter:
    model_index: int
    label_quote: str
    label_span: SourceSpan | None
    facts: tuple[M2GroundedFact, ...]


def _promotion_bindings(
    envelope: M2PromotionEnvelope,
) -> tuple[tuple[str, str, str, SourceSpan, str, SourceSpan], ...]:
    return tuple(
        (
            envelope.describe_source_ref.local_mention_id,
            "describe",
            fragment.source_evidence_quote,
            fragment.source_evidence_span,
            fragment.fragment_quote,
            fragment.fragment_span,
        )
        for fragment in envelope.remaining_fragment_bindings
    )


def _spans_overlap(left: SourceSpan, right: SourceSpan) -> bool:
    return left.start < right.end and right.start < left.end


def _subtract_claimed_fragments(
    envelope: M2PromotionEnvelope,
    claimed_spans: Iterable[SourceSpan],
) -> tuple[RemainingEvidenceFragment, ...]:
    claims = tuple(claimed_spans)
    residual: list[RemainingEvidenceFragment] = []
    residual_index = 1
    chunk_text = envelope.model_input.chunk_text
    for fragment in envelope.remaining_fragment_bindings:
        intersections = sorted(
            (
                SourceSpan(max(fragment.fragment_span.start, claim.start), min(fragment.fragment_span.end, claim.end))
                for claim in claims
                if _spans_overlap(fragment.fragment_span, claim)
            ),
            key=lambda item: (item.start, item.end),
        )
        merged: list[SourceSpan] = []
        for span in intersections:
            if merged and span.start <= merged[-1].end:
                merged[-1] = SourceSpan(merged[-1].start, max(merged[-1].end, span.end))
            else:
                merged.append(span)
        cursor = fragment.fragment_span.start
        gaps: list[SourceSpan] = []
        for span in merged:
            if cursor < span.start:
                gaps.append(SourceSpan(cursor, span.start))
            cursor = max(cursor, span.end)
        if cursor < fragment.fragment_span.end:
            gaps.append(SourceSpan(cursor, fragment.fragment_span.end))
        for gap in gaps:
            residual.append(
                RemainingEvidenceFragment(
                    fragment_ref=f"d1-f{residual_index}",
                    source_evidence_quote=fragment.source_evidence_quote,
                    source_evidence_span=fragment.source_evidence_span,
                    fragment_quote=gap.quote(chunk_text),
                    fragment_span=gap,
                )
            )
            residual_index += 1
    return tuple(residual)


def ground_m2_promotion_output(
    envelope: M2PromotionEnvelope,
    output: M2PromotionModelOutput,
) -> M2GroundedPromotionResult:
    bindings = _promotion_bindings(envelope)
    provisional: list[_ProvisionalPromotedCharacter] = []
    issues: list[M2GroundingIssue] = []

    for character_index, character in enumerate(output.characters):
        label_candidates = _fact_candidates(character.character_label_quote, bindings)
        if character.character_label_quote == envelope.model_input.mention_quote:
            label_quote = envelope.model_input.mention_quote
            label_span = None
        elif len(label_candidates) == 1:
            label_quote = label_candidates[0].raw_fact_quote
            label_span = label_candidates[0].fact_chunk_span
        else:
            code = "ambiguous_character_label" if label_candidates else "character_label_not_in_remaining_evidence"
            issues.append(
                M2GroundingIssue(
                    code,
                    None,
                    f"character {character_index} label matched {len(label_candidates)} occurrences",
                    character_index=character_index,
                    candidate_occurrence_count=len(label_candidates),
                )
            )
            continue
        grounded_facts: list[M2GroundedFact] = []
        for fact_index, fact in enumerate(character.belongs_to_character):
            candidates = _fact_candidates(fact.fact_quote, bindings)
            if len(candidates) != 1:
                code = "ambiguous_promotion_fact" if candidates else "promotion_fact_not_in_remaining_evidence"
                issues.append(
                    M2GroundingIssue(
                        code,
                        fact_index,
                        (
                            f"character {character_index} fact {fact.fact_quote!r} "
                            f"matched {len(candidates)} occurrences"
                        ),
                        character_index=character_index,
                        fact_quote=fact.fact_quote,
                        candidate_occurrence_count=len(candidates),
                    )
                )
                continue
            candidate = candidates[0]
            grounded_facts.append(
                M2GroundedFact(
                    fact_quote=candidate.raw_fact_quote,
                    category=fact.category,
                    attribute=fact.attribute,
                    value=fact.value,
                    source_mention_id=candidate.source_mention_id,
                    source_mention_type="describe",
                    source_evidence_quote=candidate.source_evidence_quote,
                    source_evidence_span=candidate.source_evidence_span,
                    fact_chunk_span=candidate.fact_chunk_span,
                    match_mode=candidate.match_mode,
                )
            )
        if grounded_facts:
            provisional.append(
                _ProvisionalPromotedCharacter(
                    model_index=character_index,
                    label_quote=label_quote,
                    label_span=label_span,
                    facts=tuple(grounded_facts),
                )
            )

    invalid: set[int] = set()
    for left_index, left in enumerate(provisional):
        for right in provisional[left_index + 1 :]:
            facts_overlap = any(
                _spans_overlap(left_fact.fact_chunk_span, right_fact.fact_chunk_span)
                for left_fact in left.facts
                for right_fact in right.facts
            )
            labels_collide = (
                left.label_quote == right.label_quote
                or (
                    left.label_span is not None
                    and right.label_span is not None
                    and _spans_overlap(left.label_span, right.label_span)
                )
            )
            if facts_overlap or labels_collide:
                invalid.update({left.model_index, right.model_index})
    for model_index in sorted(invalid):
        issues.append(
            M2GroundingIssue(
                "promotion_character_overlap",
                model_index,
                "character label or fact span overlaps another promoted character",
                character_index=model_index,
            )
        )

    valid = [item for item in provisional if item.model_index not in invalid]
    valid.sort(
        key=lambda item: (
            min(fact.fact_chunk_span.start for fact in item.facts),
            item.label_span.start if item.label_span is not None else -1,
            item.model_index,
        )
    )
    promoted: list[M2GroundedPromotedCharacter] = []
    for promotion_index, item in enumerate(valid, start=1):
        promoted.append(
            M2GroundedPromotedCharacter(
                promoted_character_ref=PromotedDescribeCharacterRef(
                    source_document_version_id=envelope.source_document_version_id,
                    chunk_id=envelope.chunk_id,
                    source_local_mention_id=envelope.describe_source_ref.local_mention_id,
                    promotion_index=promotion_index,
                    packet_hash=envelope.describe_source_ref.packet_hash,
                    promotion_hash=envelope.promotion_hash,
                ),
                character_label_quote=item.label_quote,
                grounded_belongs_to_character=item.facts,
            )
        )
    claimed_spans = tuple(
        fact.fact_chunk_span
        for character in promoted
        for fact in character.grounded_belongs_to_character
    )
    return M2GroundedPromotionResult(
        describe_source_ref=envelope.describe_source_ref,
        promotion_hash=envelope.promotion_hash,
        promoted_characters=tuple(promoted),
        unassigned_fragments=_subtract_claimed_fragments(envelope, claimed_spans),
        issues=tuple(issues),
    )


class M2PromotionOrchestrator:
    def __init__(self, provider: M2Provider) -> None:
        self._provider = provider

    def run(self, envelope: M2PromotionEnvelope) -> M2GroundedPromotionResult:
        request = M2ProviderRequest(
            system_instruction=M2_PROMOTION_SYSTEM_INSTRUCTION,
            user_payload=copy.deepcopy(envelope.model_payload()),
            response_schema=copy.deepcopy(M2_PROMOTION_RESPONSE_SCHEMA),
            response_schema_name="m2_promote_remaining_describe",
        )
        output = M2PromotionModelOutput.parse(self._provider.generate(request))
        return ground_m2_promotion_output(envelope, output)
