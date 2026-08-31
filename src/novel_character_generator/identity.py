from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from difflib import SequenceMatcher
from hashlib import sha256
from typing import Any, Iterable, Mapping, Protocol, Sequence, runtime_checkable

from .errors import ContractValidationError
from .text import SourceSpan, find_occurrences, find_safe_quote_matches, sha256_text

IDENTITY_LOCAL_NODES_VERSION = "document-local-character-nodes-v1"
IDENTITY_CONTEXT_POLICY_VERSION = "identity-evidence-window-v1"
IDENTITY_ENVELOPE_VERSION = "m3-identity-envelope-v1"
IDENTITY_GROUNDED_DECISION_VERSION = "grounded-identity-decision-v1"
IDENTITY_REGISTRY_VERSION = "document-character-registry-v1"
IDENTITY_POLICY_VERSION = "strict-evidence-identity-v1"
IDENTITY_CANDIDATE_POLICY_VERSION = "bounded-local-candidate-retrieval-v1"
IDENTITY_CONFLICT_POLICY_VERSION = "preserve-multiple-values-v1"

IDENTITY_RELATIONS = ("same_character", "different_characters", "uncertain")
LABEL_RELATIONS = (
    "same_surface",
    "name_variant",
    "alias",
    "title",
    "contextual_description",
    "unknown",
)

M3_IDENTITY_SYSTEM_INSTRUCTION = """
你只判断 current_character 与 candidate_character 是否指向同一个小说人物。

严格遵守以下规则：

1. 只能使用 payload 中的 context_quotes、appearance_fact_quotes 和 bridge_context_quotes；不得使用作品常识或外部知识。
2. 相同名字、名字相似、外貌相似、相同衣着、相同职业或位置接近都只能作为候选信号，不能单独证明同一人物。
3. 外貌不同不能单独证明是不同人物，因为人物可能换装、成长、受伤或伪装。
4. same_character 或 different_characters 必须有明确原文支持；identity_evidence_quotes 必须从输入 context 原文中连续逐字复制，不改写、不概括、不拼接。
5. 信息不足、存在多个可能人物或只能依赖弱信号时返回 uncertain。
6. label_relation 描述 current_character.label_quote 相对 candidate_character 的关系；只有 same_character 时可以非 null。
7. 不输出人物 ID、ref、span、hash、置信度、解释或 response schema 之外的字段。
"""

M3_IDENTITY_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["identity_relation", "label_relation", "identity_evidence_quotes"],
    "properties": {
        "identity_relation": {"type": "string", "enum": list(IDENTITY_RELATIONS)},
        "label_relation": {
            "anyOf": [
                {"type": "string", "enum": list(LABEL_RELATIONS)},
                {"type": "null"},
            ]
        },
        "identity_evidence_quotes": {
            "type": "array",
            "items": {"type": "string", "minLength": 1},
            "uniqueItems": True,
        },
    },
    "allOf": [
        {
            "if": {"properties": {"identity_relation": {"const": "same_character"}}},
            "then": {
                "properties": {
                    "label_relation": {"type": "string", "enum": list(LABEL_RELATIONS)},
                    "identity_evidence_quotes": {"minItems": 1},
                }
            },
        },
        {
            "if": {"properties": {"identity_relation": {"const": "different_characters"}}},
            "then": {
                "properties": {
                    "label_relation": {"type": "null"},
                    "identity_evidence_quotes": {"minItems": 1},
                }
            },
        },
        {
            "if": {"properties": {"identity_relation": {"const": "uncertain"}}},
            "then": {
                "properties": {
                    "label_relation": {"type": "null"},
                    "identity_evidence_quotes": {"maxItems": 0},
                }
            },
        },
    ],
}


def _canonical_hash(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(payload.encode("utf-8")).hexdigest()


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ContractValidationError(f"{label} must be an object")
    return value


def _sequence(value: object, label: str) -> Sequence[object]:
    if not isinstance(value, list):
        raise ContractValidationError(f"{label} must be an array")
    return value


def _string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractValidationError(f"{label} must be a non-empty string")
    return value


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ContractValidationError(f"{label} must be an integer")
    return value


def _span(value: object, label: str) -> SourceSpan:
    raw = _mapping(value, label)
    if set(raw) != {"start", "end"}:
        raise ContractValidationError(f"{label} must contain only start and end")
    return SourceSpan(_integer(raw["start"], f"{label}.start"), _integer(raw["end"], f"{label}.end"))


def _exact_keys(value: Mapping[str, object], expected: set[str], label: str) -> None:
    actual = set(value)
    if actual != expected:
        raise ContractValidationError(
            f"{label} fields mismatch; missing={sorted(expected - actual)}, extra={sorted(actual - expected)}"
        )


def _unique_strings(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


def _node_key(ref_type: str, source_character_ref: Mapping[str, object]) -> str:
    return _canonical_hash({"ref_type": ref_type, "source_character_ref": source_character_ref})


def _ref_identity(ref_type: str, source_character_ref: Mapping[str, object]) -> str:
    return json.dumps(
        {"ref_type": ref_type, "source_character_ref": source_character_ref},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


@dataclass(frozen=True)
class IdentityProviderRequest:
    system_instruction: str
    user_payload: Mapping[str, Any]
    response_schema: Mapping[str, Any]
    response_schema_name: str


@runtime_checkable
class IdentityProvider(Protocol):
    def generate(self, request: IdentityProviderRequest) -> str | Mapping[str, Any]: ...


@dataclass(frozen=True)
class IdentityContextBinding:
    context_quote: str
    document_span: SourceSpan
    source_kind: str

    def __post_init__(self) -> None:
        _string(self.context_quote, "context_quote")
        if self.source_kind not in {"node", "current", "candidate", "bridge"}:
            raise ContractValidationError("identity context source_kind is invalid")

    def to_dict(self) -> dict[str, object]:
        return {
            "context_quote": self.context_quote,
            "document_span": self.document_span.to_dict(),
            "source_kind": self.source_kind,
        }


@dataclass(frozen=True)
class IdentityAppearanceFactRef:
    fact_hash: str
    fact_quote: str
    category: str
    attribute: str
    value: str
    document_fact_span: SourceSpan

    def __post_init__(self) -> None:
        for label, value in (
            ("fact_hash", self.fact_hash),
            ("fact_quote", self.fact_quote),
            ("category", self.category),
            ("attribute", self.attribute),
            ("value", self.value),
        ):
            _string(value, label)

    def to_dict(self) -> dict[str, object]:
        return {
            "fact_hash": self.fact_hash,
            "fact_quote": self.fact_quote,
            "category": self.category,
            "attribute": self.attribute,
            "value": self.value,
            "document_fact_span": self.document_fact_span.to_dict(),
        }


@dataclass(frozen=True)
class LocalCharacterNode:
    node_key: str
    ref_type: str
    source_character_ref: Mapping[str, object]
    character_origin: str
    label_quote: str
    label_type: str
    chunk_id: str
    chunk_source_span: SourceSpan
    context_bindings: tuple[IdentityContextBinding, ...]
    appearance_fact_refs: tuple[IdentityAppearanceFactRef, ...]
    order_position: int

    def __post_init__(self) -> None:
        if self.ref_type not in {"local", "promoted"}:
            raise ContractValidationError("local identity node ref_type is invalid")
        if self.character_origin not in {"exact", "remaining_describe"}:
            raise ContractValidationError("local identity node character_origin is invalid")
        if self.label_type not in {"exact", "describe"}:
            raise ContractValidationError("local identity node label_type is invalid")
        _string(self.node_key, "node_key")
        _string(self.label_quote, "label_quote")
        _string(self.chunk_id, "chunk_id")
        if self.node_key != _node_key(self.ref_type, self.source_character_ref):
            raise ContractValidationError("local identity node_key does not match source ref")
        if self.order_position < self.chunk_source_span.start:
            raise ContractValidationError("local identity node order_position precedes its Chunk")

    def to_dict(self) -> dict[str, object]:
        return {
            "node_key": self.node_key,
            "ref_type": self.ref_type,
            "source_character_ref": dict(self.source_character_ref),
            "character_origin": self.character_origin,
            "label_quote": self.label_quote,
            "label_type": self.label_type,
            "chunk_id": self.chunk_id,
            "chunk_source_span": self.chunk_source_span.to_dict(),
            "context_bindings": [item.to_dict() for item in self.context_bindings],
            "appearance_fact_refs": [item.to_dict() for item in self.appearance_fact_refs],
            "order_position": self.order_position,
        }


@dataclass(frozen=True)
class DocumentLocalCharacterNodes:
    source_document_version_id: str
    document_hash: str
    nodes: tuple[LocalCharacterNode, ...]
    context_policy_version: str = IDENTITY_CONTEXT_POLICY_VERSION
    schema_version: str = IDENTITY_LOCAL_NODES_VERSION

    def to_dict(self) -> dict[str, object]:
        exact = sum(node.label_type == "exact" for node in self.nodes)
        promoted = len(self.nodes) - exact
        return {
            "schema_version": self.schema_version,
            "context_policy_version": self.context_policy_version,
            "source_document_version_id": self.source_document_version_id,
            "document_hash": self.document_hash,
            "nodes": [node.to_dict() for node in self.nodes],
            "summary": {
                "local_character_nodes": len(self.nodes),
                "exact_nodes": exact,
                "promoted_nodes": promoted,
                "nodes_without_appearance_facts": sum(not node.appearance_fact_refs for node in self.nodes),
            },
        }


@dataclass(frozen=True)
class IdentityCurrentModelInput:
    label_quote: str
    label_type: str
    context_quotes: tuple[str, ...]
    appearance_fact_quotes: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "label_quote": self.label_quote,
            "label_type": self.label_type,
            "context_quotes": list(self.context_quotes),
            "appearance_fact_quotes": list(self.appearance_fact_quotes),
        }


@dataclass(frozen=True)
class IdentityCandidateModelInput:
    known_labels: tuple[str, ...]
    context_quotes: tuple[str, ...]
    appearance_fact_quotes: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "known_labels": list(self.known_labels),
            "context_quotes": list(self.context_quotes),
            "appearance_fact_quotes": list(self.appearance_fact_quotes),
        }


@dataclass(frozen=True)
class IdentityModelInput:
    current_character: IdentityCurrentModelInput
    candidate_character: IdentityCandidateModelInput
    bridge_context_quotes: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "current_character": self.current_character.to_dict(),
            "candidate_character": self.candidate_character.to_dict(),
            "bridge_context_quotes": list(self.bridge_context_quotes),
        }


@dataclass(frozen=True)
class IdentityEnvelope:
    current_node_key: str
    candidate_node_key: str
    candidate_reasons: tuple[str, ...]
    context_bindings: tuple[IdentityContextBinding, ...]
    task_cache_key: str
    model_input: IdentityModelInput
    schema_version: str = IDENTITY_ENVELOPE_VERSION

    def __post_init__(self) -> None:
        if self.current_node_key == self.candidate_node_key:
            raise ContractValidationError("identity envelope cannot compare a node with itself")
        if not self.candidate_reasons:
            raise ContractValidationError("identity envelope requires at least one candidate reason")
        expected = _canonical_hash(
            {
                "schema_version": self.schema_version,
                "current_node_key": self.current_node_key,
                "candidate_node_key": self.candidate_node_key,
                "candidate_reasons": list(self.candidate_reasons),
                "context_policy_version": IDENTITY_CONTEXT_POLICY_VERSION,
                "model_input": self.model_input.to_dict(),
            }
        )
        if self.task_cache_key != expected:
            raise ContractValidationError("identity task_cache_key does not match envelope")

    def model_payload(self) -> dict[str, object]:
        return self.model_input.to_dict()

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "current_node_key": self.current_node_key,
            "candidate_node_key": self.candidate_node_key,
            "candidate_reasons": list(self.candidate_reasons),
            "context_bindings": [item.to_dict() for item in self.context_bindings],
            "task_cache_key": self.task_cache_key,
            "model_input": self.model_input.to_dict(),
        }


@dataclass(frozen=True)
class IdentityModelOutput:
    identity_relation: str
    label_relation: str | None
    identity_evidence_quotes: tuple[str, ...]

    @classmethod
    def parse(cls, raw: str | Mapping[str, Any]) -> IdentityModelOutput:
        if isinstance(raw, str):
            try:
                value = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ContractValidationError("M3 identity model output is invalid JSON") from exc
        else:
            value = raw
        parsed = _mapping(value, "M3 identity model output")
        _exact_keys(
            parsed,
            {"identity_relation", "label_relation", "identity_evidence_quotes"},
            "M3 identity model output",
        )
        relation = _string(parsed["identity_relation"], "identity_relation")
        if relation not in IDENTITY_RELATIONS:
            raise ContractValidationError("identity_relation is invalid")
        label_relation = parsed["label_relation"]
        if label_relation is not None:
            label_relation = _string(label_relation, "label_relation")
            if label_relation not in LABEL_RELATIONS:
                raise ContractValidationError("label_relation is invalid")
        quotes_raw = _sequence(parsed["identity_evidence_quotes"], "identity_evidence_quotes")
        quotes = tuple(_string(item, f"identity_evidence_quotes[{index}]") for index, item in enumerate(quotes_raw))
        if len(quotes) != len(set(quotes)):
            raise ContractValidationError("identity_evidence_quotes must be unique")
        if relation == "same_character":
            if label_relation is None or not quotes:
                raise ContractValidationError("same_character requires label_relation and evidence")
        elif relation == "different_characters":
            if label_relation is not None or not quotes:
                raise ContractValidationError("different_characters requires null label_relation and evidence")
        elif label_relation is not None or quotes:
            raise ContractValidationError("uncertain requires null label_relation and no evidence")
        return cls(relation, label_relation, quotes)

    def to_dict(self) -> dict[str, object]:
        return {
            "identity_relation": self.identity_relation,
            "label_relation": self.label_relation,
            "identity_evidence_quotes": list(self.identity_evidence_quotes),
        }


def _chunk_entries(document_evidence: Mapping[str, object]) -> dict[str, SourceSpan]:
    entries: dict[str, SourceSpan] = {}
    for index, raw in enumerate(_sequence(document_evidence.get("source_chunks"), "source_chunks")):
        item = _mapping(raw, f"source_chunks[{index}]")
        chunk_id = _string(item.get("chunk_id"), "source chunk_id")
        if chunk_id in entries:
            raise ContractValidationError("duplicate source chunk in document evidence")
        entries[chunk_id] = _span(item.get("chunk_source_span"), "chunk_source_span")
    return entries


def _window_span(anchor: SourceSpan, chunk_span: SourceSpan, radius: int) -> SourceSpan:
    if radius < 0:
        raise ContractValidationError("identity context radius cannot be negative")
    start = max(chunk_span.start, anchor.start - radius)
    end = min(chunk_span.end, anchor.end + radius)
    return SourceSpan(start, end)


def _node_contexts(
    *,
    document_text: str,
    chunk_span: SourceSpan,
    anchor_spans: Iterable[SourceSpan],
    label_quote: str,
    context_radius: int,
    max_contexts: int,
) -> tuple[IdentityContextBinding, ...]:
    spans = {_window_span(anchor, chunk_span, context_radius) for anchor in anchor_spans}
    if not spans:
        chunk_text = chunk_span.quote(document_text)
        for local in find_occurrences(chunk_text, label_quote)[:max_contexts]:
            absolute = SourceSpan(chunk_span.start + local.start, chunk_span.start + local.end)
            spans.add(_window_span(absolute, chunk_span, context_radius))
    ordered = sorted(spans, key=lambda item: (item.start, item.end))[:max_contexts]
    return tuple(
        IdentityContextBinding(span.quote(document_text), span, "node")
        for span in ordered
    )


def build_document_local_character_nodes(
    *,
    document_text: str,
    source_n2_packets: Sequence[object],
    n3_target_packets: Sequence[object],
    promotion_grounded_results: Sequence[object],
    document_evidence: Mapping[str, object],
    context_radius: int = 240,
    max_contexts_per_node: int = 4,
) -> DocumentLocalCharacterNodes:
    """Build the complete exact/promoted local-person catalog used by identity resolution."""
    if max_contexts_per_node < 1:
        raise ContractValidationError("max_contexts_per_node must be at least one")
    source_version = _string(
        document_evidence.get("source_document_version_id"),
        "document evidence source_document_version_id",
    )
    document_hash = _string(document_evidence.get("document_hash"), "document evidence document_hash")
    if document_hash != sha256_text(document_text):
        raise ContractValidationError("identity document text does not match document evidence hash")
    chunks = _chunk_entries(document_evidence)

    exact_metadata: dict[str, tuple[str, SourceSpan, tuple[SourceSpan, ...]]] = {}
    for packet_index, raw_packet in enumerate(source_n2_packets):
        packet = _mapping(raw_packet, f"source_n2_packets[{packet_index}]")
        if _string(packet.get("source_document_version_id"), "N2 source version") != source_version:
            raise ContractValidationError("N2 identity source belongs to another document")
        chunk_id = _string(packet.get("chunk_id"), "N2 chunk_id")
        chunk_span = _span(packet.get("chunk_source_span"), "N2 chunk_source_span")
        if chunks.get(chunk_id) != chunk_span:
            raise ContractValidationError("N2 identity Chunk span does not match document evidence")
        for mention_index, raw_mention in enumerate(_sequence(packet.get("grounded_mentions"), "N2 mentions")):
            mention = _mapping(raw_mention, f"N2 mentions[{mention_index}]")
            if mention.get("mention_type") != "exact":
                continue
            source_ref = {
                "source_document_version_id": source_version,
                "chunk_id": chunk_id,
                "local_mention_id": _string(mention.get("local_mention_id"), "local_mention_id"),
                "mention_type": "exact",
                "packet_hash": _string(mention.get("packet_hash"), "packet_hash"),
            }
            anchors: list[SourceSpan] = []
            for evidence_index, raw_evidence in enumerate(
                _sequence(mention.get("approved_evidence"), "approved_evidence")
            ):
                evidence = _mapping(raw_evidence, f"approved_evidence[{evidence_index}]")
                for span_index, raw_span in enumerate(_sequence(evidence.get("source_spans"), "source_spans")):
                    local = _span(raw_span, f"source_spans[{span_index}]")
                    if local.end > chunk_span.end - chunk_span.start:
                        raise ContractValidationError("N2 evidence span exceeds identity source Chunk")
                    anchors.append(SourceSpan(chunk_span.start + local.start, chunk_span.start + local.end))
            exact_metadata[_ref_identity("local", source_ref)] = (
                _string(mention.get("mention_quote"), "mention_quote"),
                chunk_span,
                tuple(anchors),
            )

    facts_by_ref: dict[str, dict[str, IdentityAppearanceFactRef]] = {}
    anchors_by_ref: dict[str, set[SourceSpan]] = {}
    for fact_index, raw_fact in enumerate(_sequence(document_evidence.get("appearance_facts"), "appearance_facts")):
        fact = _mapping(raw_fact, f"appearance_facts[{fact_index}]")
        fact_ref = IdentityAppearanceFactRef(
            fact_hash=_string(fact.get("fact_hash"), "fact_hash"),
            fact_quote=_string(fact.get("fact_quote"), "fact_quote"),
            category=_string(fact.get("category"), "category"),
            attribute=_string(fact.get("attribute"), "attribute"),
            value=_string(fact.get("value"), "value"),
            document_fact_span=_span(fact.get("document_fact_span"), "document_fact_span"),
        )
        if fact_ref.document_fact_span.quote(document_text) != fact_ref.fact_quote:
            raise ContractValidationError("identity fact does not replay against document")
        for occurrence_index, raw_occurrence in enumerate(
            _sequence(fact.get("source_occurrences"), "source_occurrences")
        ):
            occurrence = _mapping(raw_occurrence, f"source_occurrences[{occurrence_index}]")
            source_ref = _mapping(occurrence.get("source_character_ref"), "source_character_ref")
            ref_type = "local" if source_ref.get("mention_type") == "exact" else "promoted"
            identity = _ref_identity(ref_type, source_ref)
            facts_by_ref.setdefault(identity, {})[fact_ref.fact_hash] = fact_ref
            evidence_span = _span(occurrence.get("document_evidence_span"), "document_evidence_span")
            evidence_quote = _string(occurrence.get("source_evidence_quote"), "source_evidence_quote")
            if evidence_span.quote(document_text) != evidence_quote:
                raise ContractValidationError("identity evidence context does not replay against document")
            anchors_by_ref.setdefault(identity, set()).add(evidence_span)

    nodes: list[LocalCharacterNode] = []
    seen_refs: set[str] = set()
    for packet_index, raw_packet in enumerate(n3_target_packets):
        packet = _mapping(raw_packet, f"n3_target_packets[{packet_index}]")
        source_ref = _mapping(packet.get("target_character_ref"), "target_character_ref")
        identity = _ref_identity("local", source_ref)
        if identity in seen_refs:
            raise ContractValidationError("duplicate exact local character node")
        metadata = exact_metadata.get(identity)
        if metadata is None:
            raise ContractValidationError("N3 exact ref cannot be resolved to N2 identity metadata")
        label, chunk_span, fallback_anchors = metadata
        anchors = tuple(sorted(anchors_by_ref.get(identity, set()))) or fallback_anchors
        contexts = _node_contexts(
            document_text=document_text,
            chunk_span=chunk_span,
            anchor_spans=anchors,
            label_quote=label,
            context_radius=context_radius,
            max_contexts=max_contexts_per_node,
        )
        facts = tuple(sorted(facts_by_ref.get(identity, {}).values(), key=lambda item: (item.document_fact_span, item.fact_hash)))
        order = min((item.document_span.start for item in contexts), default=chunk_span.start)
        nodes.append(
            LocalCharacterNode(
                node_key=_node_key("local", source_ref),
                ref_type="local",
                source_character_ref=dict(source_ref),
                character_origin="exact",
                label_quote=label,
                label_type="exact",
                chunk_id=_string(source_ref.get("chunk_id"), "exact ref chunk_id"),
                chunk_source_span=chunk_span,
                context_bindings=contexts,
                appearance_fact_refs=facts,
                order_position=order,
            )
        )
        seen_refs.add(identity)

    for wrapper_index, raw_wrapper in enumerate(promotion_grounded_results):
        wrapper = _mapping(raw_wrapper, f"promotion_grounded_results[{wrapper_index}]")
        grounded = _mapping(wrapper.get("grounded_result"), "promotion grounded_result")
        for character_index, raw_character in enumerate(
            _sequence(grounded.get("promoted_characters"), "promoted_characters")
        ):
            character = _mapping(raw_character, f"promoted_characters[{character_index}]")
            source_ref = _mapping(character.get("promoted_character_ref"), "promoted_character_ref")
            if _string(source_ref.get("source_document_version_id"), "promoted source version") != source_version:
                raise ContractValidationError("promoted identity source belongs to another document")
            identity = _ref_identity("promoted", source_ref)
            if identity in seen_refs:
                raise ContractValidationError("duplicate promoted local character node")
            chunk_id = _string(source_ref.get("chunk_id"), "promoted ref chunk_id")
            chunk_span = chunks.get(chunk_id)
            if chunk_span is None:
                raise ContractValidationError("promoted identity node references unknown Chunk")
            label = _string(character.get("character_label_quote"), "character_label_quote")
            anchors = tuple(sorted(anchors_by_ref.get(identity, set())))
            contexts = _node_contexts(
                document_text=document_text,
                chunk_span=chunk_span,
                anchor_spans=anchors,
                label_quote=label,
                context_radius=context_radius,
                max_contexts=max_contexts_per_node,
            )
            facts = tuple(
                sorted(facts_by_ref.get(identity, {}).values(), key=lambda item: (item.document_fact_span, item.fact_hash))
            )
            order = min((item.document_span.start for item in contexts), default=chunk_span.start)
            nodes.append(
                LocalCharacterNode(
                    node_key=_node_key("promoted", source_ref),
                    ref_type="promoted",
                    source_character_ref=dict(source_ref),
                    character_origin="remaining_describe",
                    label_quote=label,
                    label_type="describe",
                    chunk_id=chunk_id,
                    chunk_source_span=chunk_span,
                    context_bindings=contexts,
                    appearance_fact_refs=facts,
                    order_position=order,
                )
            )
            seen_refs.add(identity)

    nodes.sort(key=lambda item: (item.order_position, item.chunk_id, item.node_key))
    return DocumentLocalCharacterNodes(source_version, document_hash, tuple(nodes))


def _normalized_label(value: str) -> str:
    return "".join(character.lower() for character in value if not character.isspace())


def _candidate_signals(current: LocalCharacterNode, candidate: LocalCharacterNode) -> tuple[int, tuple[str, ...]]:
    left = _normalized_label(current.label_quote)
    right = _normalized_label(candidate.label_quote)
    reasons: list[str] = []
    score = 0
    both_describe = current.label_type == candidate.label_type == "describe"
    if left == right and not both_describe:
        score = max(score, 100)
        reasons.append("same_exact_label")
    shorter, longer = (left, right) if len(left) <= len(right) else (right, left)
    if len(shorter) >= 2 and shorter != longer and shorter in longer:
        score = max(score, 90)
        reasons.append("label_contains")
    if (
        current.label_type == candidate.label_type == "exact"
        and len(left) == len(right)
        and len(left) >= 3
        and left != right
        and SequenceMatcher(None, left, right).ratio() >= 2 / 3
    ):
        score = max(score, 80)
        reasons.append("possible_name_variant")
    current_quotes = {item.fact_quote for item in current.appearance_fact_refs}
    candidate_quotes = {item.fact_quote for item in candidate.appearance_fact_refs}
    if current_quotes & candidate_quotes:
        score = max(score, 65)
        reasons.append("shared_fact_quote")
    return score, tuple(reasons)


def _retyped_contexts(node: LocalCharacterNode, source_kind: str) -> tuple[IdentityContextBinding, ...]:
    return tuple(
        IdentityContextBinding(item.context_quote, item.document_span, source_kind)
        for item in node.context_bindings
    )


def _bridge_context(
    current: LocalCharacterNode,
    candidate: LocalCharacterNode,
    document_text: str,
    max_bridge_characters: int,
) -> tuple[IdentityContextBinding, ...]:
    pairs = [
        (abs(left.document_span.start - right.document_span.start), left, right)
        for left in current.context_bindings
        for right in candidate.context_bindings
    ]
    if not pairs:
        return ()
    _, left, right = min(pairs, key=lambda item: (item[0], item[1].document_span, item[2].document_span))
    span = SourceSpan(
        min(left.document_span.start, right.document_span.start),
        max(left.document_span.end, right.document_span.end),
    )
    if span.end - span.start > max_bridge_characters:
        return ()
    return (IdentityContextBinding(span.quote(document_text), span, "bridge"),)


@dataclass(frozen=True)
class IdentityPreparation:
    local_nodes: DocumentLocalCharacterNodes
    deterministic_edges: tuple[Mapping[str, object], ...]
    envelopes: tuple[IdentityEnvelope, ...]
    candidate_policy_version: str = IDENTITY_CANDIDATE_POLICY_VERSION

    def summary(self) -> dict[str, object]:
        return {
            "schema_version": "identity-preparation-summary-v1",
            "candidate_policy_version": self.candidate_policy_version,
            "local_character_nodes": len(self.local_nodes.nodes),
            "deterministic_same_edges": len(self.deterministic_edges),
            "pending_model_tasks": len(self.envelopes),
            "provider_calls": 0,
            "complete": True,
        }


def build_identity_preparation(
    *,
    local_nodes: DocumentLocalCharacterNodes,
    document_text: str,
    max_candidates_per_node: int = 2,
    max_bridge_characters: int = 1200,
) -> IdentityPreparation:
    if max_candidates_per_node < 1:
        raise ContractValidationError("max_candidates_per_node must be at least one")
    if max_bridge_characters < 1:
        raise ContractValidationError("max_bridge_characters must be at least one")
    if sha256_text(document_text) != local_nodes.document_hash:
        raise ContractValidationError("identity preparation document hash mismatch")
    nodes = local_nodes.nodes
    deterministic_edges: list[Mapping[str, object]] = []
    deterministic_pairs: set[frozenset[str]] = set()
    fact_sets = {node.node_key: {fact.fact_hash for fact in node.appearance_fact_refs} for node in nodes}
    for left_index, left in enumerate(nodes):
        for right in nodes[left_index + 1 :]:
            shared = sorted(fact_sets[left.node_key] & fact_sets[right.node_key])
            if not shared:
                continue
            pair = frozenset({left.node_key, right.node_key})
            deterministic_pairs.add(pair)
            deterministic_edges.append(
                {
                    "left_node_key": left.node_key,
                    "right_node_key": right.node_key,
                    "relation": "same_character",
                    "reason": "shared_document_fact",
                    "fact_hashes": shared,
                }
            )

    envelopes: list[IdentityEnvelope] = []
    for current_index, current in enumerate(nodes):
        scored: list[tuple[int, int, LocalCharacterNode, tuple[str, ...]]] = []
        for candidate in nodes[:current_index]:
            if frozenset({current.node_key, candidate.node_key}) in deterministic_pairs:
                continue
            score, reasons = _candidate_signals(current, candidate)
            if score == 0:
                continue
            distance = abs(current.order_position - candidate.order_position)
            scored.append((score, distance, candidate, reasons))
        scored.sort(key=lambda item: (-item[0], item[1], item[2].order_position, item[2].node_key))
        for _, _, candidate, reasons in scored[:max_candidates_per_node]:
            current_contexts = _retyped_contexts(current, "current")
            candidate_contexts = _retyped_contexts(candidate, "candidate")
            bridge = _bridge_context(current, candidate, document_text, max_bridge_characters)
            model_input = IdentityModelInput(
                current_character=IdentityCurrentModelInput(
                    label_quote=current.label_quote,
                    label_type=current.label_type,
                    context_quotes=_unique_strings(item.context_quote for item in current_contexts),
                    appearance_fact_quotes=_unique_strings(
                        item.fact_quote for item in current.appearance_fact_refs
                    ),
                ),
                candidate_character=IdentityCandidateModelInput(
                    known_labels=(candidate.label_quote,),
                    context_quotes=_unique_strings(item.context_quote for item in candidate_contexts),
                    appearance_fact_quotes=_unique_strings(
                        item.fact_quote for item in candidate.appearance_fact_refs
                    ),
                ),
                bridge_context_quotes=_unique_strings(item.context_quote for item in bridge),
            )
            hash_input = {
                "schema_version": IDENTITY_ENVELOPE_VERSION,
                "current_node_key": current.node_key,
                "candidate_node_key": candidate.node_key,
                "candidate_reasons": list(reasons),
                "context_policy_version": IDENTITY_CONTEXT_POLICY_VERSION,
                "model_input": model_input.to_dict(),
            }
            envelopes.append(
                IdentityEnvelope(
                    current_node_key=current.node_key,
                    candidate_node_key=candidate.node_key,
                    candidate_reasons=reasons,
                    context_bindings=current_contexts + candidate_contexts + bridge,
                    task_cache_key=_canonical_hash(hash_input),
                    model_input=model_input,
                )
            )
    return IdentityPreparation(local_nodes, tuple(deterministic_edges), tuple(envelopes))


@dataclass(frozen=True)
class GroundedIdentityEvidence:
    evidence_quote: str
    document_span: SourceSpan
    match_mode: str

    def __post_init__(self) -> None:
        _string(self.evidence_quote, "grounded identity evidence_quote")
        if self.match_mode not in {"exact", "whitespace_equivalent"}:
            raise ContractValidationError("grounded identity evidence match_mode is invalid")

    def to_dict(self) -> dict[str, object]:
        return {
            "evidence_quote": self.evidence_quote,
            "document_span": self.document_span.to_dict(),
            "match_mode": self.match_mode,
        }


@dataclass(frozen=True)
class IdentityGroundingIssue:
    code: str
    evidence_index: int | None
    evidence_quote: str | None
    candidate_occurrence_count: int | None
    detail: str

    def __post_init__(self) -> None:
        _string(self.code, "identity grounding issue code")
        _string(self.detail, "identity grounding issue detail")
        if self.evidence_index is not None and self.evidence_index < 0:
            raise ContractValidationError("identity grounding issue evidence_index cannot be negative")
        if self.candidate_occurrence_count is not None and self.candidate_occurrence_count < 0:
            raise ContractValidationError("identity grounding occurrence count cannot be negative")

    def to_dict(self) -> dict[str, object]:
        value: dict[str, object] = {"code": self.code, "detail": self.detail}
        if self.evidence_index is not None:
            value["evidence_index"] = self.evidence_index
        if self.evidence_quote is not None:
            value["evidence_quote"] = self.evidence_quote
        if self.candidate_occurrence_count is not None:
            value["candidate_occurrence_count"] = self.candidate_occurrence_count
        return value


@dataclass(frozen=True)
class GroundedIdentityDecision:
    current_node_key: str
    candidate_node_key: str
    task_cache_key: str
    requested_identity_relation: str
    identity_relation: str
    label_relation: str | None
    grounded_identity_evidence: tuple[GroundedIdentityEvidence, ...]
    issues: tuple[IdentityGroundingIssue, ...]
    schema_version: str = IDENTITY_GROUNDED_DECISION_VERSION

    def __post_init__(self) -> None:
        for label, value in (
            ("current_node_key", self.current_node_key),
            ("candidate_node_key", self.candidate_node_key),
            ("task_cache_key", self.task_cache_key),
        ):
            _string(value, label)
        if self.current_node_key == self.candidate_node_key:
            raise ContractValidationError("grounded identity decision cannot compare a node with itself")
        if self.requested_identity_relation not in IDENTITY_RELATIONS:
            raise ContractValidationError("requested identity relation is invalid")
        if self.identity_relation not in IDENTITY_RELATIONS:
            raise ContractValidationError("grounded identity relation is invalid")
        if self.identity_relation == "same_character":
            if self.label_relation not in LABEL_RELATIONS or not self.grounded_identity_evidence:
                raise ContractValidationError("grounded same_character requires label relation and evidence")
        elif self.identity_relation == "different_characters":
            if self.label_relation is not None or not self.grounded_identity_evidence:
                raise ContractValidationError("grounded different_characters requires evidence and no label relation")
        elif self.label_relation is not None or self.grounded_identity_evidence:
            raise ContractValidationError("grounded uncertain requires no label relation or accepted evidence")
        if self.identity_relation != self.requested_identity_relation and self.identity_relation != "uncertain":
            raise ContractValidationError("grounding may only preserve or downgrade an identity relation")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "current_node_key": self.current_node_key,
            "candidate_node_key": self.candidate_node_key,
            "task_cache_key": self.task_cache_key,
            "requested_identity_relation": self.requested_identity_relation,
            "identity_relation": self.identity_relation,
            "label_relation": self.label_relation,
            "grounded_identity_evidence": [item.to_dict() for item in self.grounded_identity_evidence],
            "issues": [item.to_dict() for item in self.issues],
        }


def ground_identity_model_output(
    envelope: IdentityEnvelope,
    output: IdentityModelOutput,
    *,
    document_text: str,
) -> GroundedIdentityDecision:
    if output.identity_relation == "uncertain":
        return GroundedIdentityDecision(
            envelope.current_node_key,
            envelope.candidate_node_key,
            envelope.task_cache_key,
            output.identity_relation,
            "uncertain",
            None,
            (),
            (),
        )
    candidates_by_quote: dict[str, list[GroundedIdentityEvidence]] = {}
    for binding in envelope.context_bindings:
        if binding.document_span.quote(document_text) != binding.context_quote:
            raise ContractValidationError("identity context binding no longer replays against document")
        for model_quote in output.identity_evidence_quotes:
            for match in find_safe_quote_matches(binding.context_quote, model_quote):
                absolute = SourceSpan(
                    binding.document_span.start + match.span.start,
                    binding.document_span.start + match.span.end,
                )
                evidence = GroundedIdentityEvidence(match.raw_quote, absolute, match.match_mode)
                existing = candidates_by_quote.setdefault(model_quote, [])
                if all(
                    (item.document_span, item.evidence_quote) != (evidence.document_span, evidence.evidence_quote)
                    for item in existing
                ):
                    existing.append(evidence)

    grounded: list[GroundedIdentityEvidence] = []
    issues: list[IdentityGroundingIssue] = []
    for evidence_index, quote in enumerate(output.identity_evidence_quotes):
        candidates = candidates_by_quote.get(quote, [])
        if len(candidates) == 1:
            grounded.append(candidates[0])
            continue
        code = "ambiguous_identity_evidence" if candidates else "identity_evidence_not_in_model_context"
        issues.append(
            IdentityGroundingIssue(
                code=code,
                evidence_index=evidence_index,
                evidence_quote=quote,
                candidate_occurrence_count=len(candidates),
                detail=f"identity evidence {quote!r} matched {len(candidates)} document occurrences",
            )
        )
    grounded.sort(key=lambda item: (item.document_span, item.evidence_quote))
    accepted_relation = output.identity_relation if grounded else "uncertain"
    if not grounded:
        issues.append(
            IdentityGroundingIssue(
                code="identity_relation_without_grounded_evidence",
                evidence_index=None,
                evidence_quote=None,
                candidate_occurrence_count=None,
                detail="non-uncertain identity relation was downgraded because no evidence grounded safely",
            )
        )
    return GroundedIdentityDecision(
        current_node_key=envelope.current_node_key,
        candidate_node_key=envelope.candidate_node_key,
        task_cache_key=envelope.task_cache_key,
        requested_identity_relation=output.identity_relation,
        identity_relation=accepted_relation,
        label_relation=output.label_relation if accepted_relation == "same_character" else None,
        grounded_identity_evidence=tuple(grounded),
        issues=tuple(issues),
    )


class IdentityOrchestrator:
    def __init__(self, provider: IdentityProvider) -> None:
        self._provider = provider

    def run(self, envelope: IdentityEnvelope, *, document_text: str) -> GroundedIdentityDecision:
        request = IdentityProviderRequest(
            system_instruction=M3_IDENTITY_SYSTEM_INSTRUCTION,
            user_payload=copy.deepcopy(envelope.model_payload()),
            response_schema=copy.deepcopy(M3_IDENTITY_RESPONSE_SCHEMA),
            response_schema_name="m3_character_identity_relation",
        )
        output = IdentityModelOutput.parse(self._provider.generate(request))
        return ground_identity_model_output(envelope, output, document_text=document_text)


class _UnionFind:
    def __init__(self, keys: Iterable[str]) -> None:
        self.parent = {key: key for key in keys}

    def find(self, key: str) -> str:
        parent = self.parent[key]
        if parent != key:
            self.parent[key] = self.find(parent)
        return self.parent[key]

    def union(self, left: str, right: str) -> str:
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root == right_root:
            return left_root
        keep, absorb = sorted((left_root, right_root))
        self.parent[absorb] = keep
        return keep

    def members(self, key: str) -> set[str]:
        root = self.find(key)
        return {candidate for candidate in self.parent if self.find(candidate) == root}


def _wrapped_ref(node: LocalCharacterNode) -> dict[str, object]:
    return {
        "ref_type": node.ref_type,
        f"{node.ref_type}_character_ref": dict(node.source_character_ref),
    }


def _clusters_have_cannot_link(
    union_find: _UnionFind,
    left: str,
    right: str,
    cannot_links: set[frozenset[str]],
) -> bool:
    left_members = union_find.members(left)
    right_members = union_find.members(right)
    return any(frozenset({a, b}) in cannot_links for a in left_members for b in right_members if a != b)


def _character_id(source_version: str, members: Sequence[LocalCharacterNode]) -> str:
    anchor = min(members, key=lambda item: (item.order_position, item.node_key))
    digest = _canonical_hash(
        {
            "source_document_version_id": source_version,
            "identity_policy_version": IDENTITY_POLICY_VERSION,
            "anchor_node_key": anchor.node_key,
        }
    )
    return f"char-{digest[:20]}"


def _canonical_node(members: Sequence[LocalCharacterNode]) -> LocalCharacterNode:
    counts: dict[str, int] = {}
    for node in members:
        counts[node.label_quote] = counts.get(node.label_quote, 0) + 1
    return min(
        members,
        key=lambda item: (
            0 if item.label_type == "exact" else 1,
            -counts[item.label_quote],
            -len(item.label_quote),
            item.order_position,
            item.node_key,
        ),
    )


def _label_role(node: LocalCharacterNode, canonical: LocalCharacterNode, accepted_roles: Mapping[str, str]) -> str:
    if node.label_quote == canonical.label_quote and canonical.label_type == "exact":
        return "name"
    accepted = accepted_roles.get(node.node_key)
    if accepted == "same_surface":
        return "name" if node.label_type == "exact" else "contextual_description"
    if accepted in {"name_variant", "alias", "title", "contextual_description", "unknown"}:
        return accepted
    return "alias" if node.label_type == "exact" else "contextual_description"


def _possible_conflicts(
    character_id: str,
    fact_refs: Sequence[IdentityAppearanceFactRef],
) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str], list[IdentityAppearanceFactRef]] = {}
    for fact in fact_refs:
        grouped.setdefault((fact.category, fact.attribute), []).append(fact)
    conflicts: list[dict[str, object]] = []
    for (category, attribute), facts in sorted(grouped.items()):
        values = sorted({fact.value for fact in facts})
        if len(values) < 2:
            continue
        fact_hashes = sorted({fact.fact_hash for fact in facts})
        conflict_id = "conflict-" + _canonical_hash(
            {
                "character_id": character_id,
                "category": category,
                "attribute": attribute,
                "fact_hashes": fact_hashes,
                "policy": IDENTITY_CONFLICT_POLICY_VERSION,
            }
        )[:20]
        conflicts.append(
            {
                "conflict_id": conflict_id,
                "conflict_type": "multiple_values_same_attribute",
                "category": category,
                "attribute": attribute,
                "fact_hashes": fact_hashes,
                "values": values,
                "resolution_status": "unresolved",
            }
        )
    return conflicts


def _review_id(node_key: str, review_type: str, candidate_keys: Iterable[str]) -> str:
    return "review-" + _canonical_hash(
        {
            "node_key": node_key,
            "review_type": review_type,
            "candidate_keys": sorted(candidate_keys),
            "identity_policy_version": IDENTITY_POLICY_VERSION,
        }
    )[:20]


def build_document_character_registry(
    *,
    preparation: IdentityPreparation,
    grounded_decisions: Sequence[GroundedIdentityDecision],
) -> dict[str, object]:
    """Apply fail-closed identity decisions and aggregate already-grounded facts."""
    nodes = preparation.local_nodes.nodes
    node_by_key = {node.node_key: node for node in nodes}
    if len(node_by_key) != len(nodes):
        raise ContractValidationError("identity registry received duplicate node keys")
    envelope_by_task = {envelope.task_cache_key: envelope for envelope in preparation.envelopes}
    if len(envelope_by_task) != len(preparation.envelopes):
        raise ContractValidationError("identity preparation contains duplicate task cache keys")
    decision_by_task: dict[str, GroundedIdentityDecision] = {}
    for decision in grounded_decisions:
        envelope = envelope_by_task.get(decision.task_cache_key)
        if envelope is None:
            raise ContractValidationError("identity decision does not belong to this preparation")
        if (
            decision.current_node_key != envelope.current_node_key
            or decision.candidate_node_key != envelope.candidate_node_key
        ):
            raise ContractValidationError("identity decision node binding does not match its envelope")
        if decision.task_cache_key in decision_by_task:
            raise ContractValidationError("duplicate grounded identity decision")
        decision_by_task[decision.task_cache_key] = decision
    if set(decision_by_task) != set(envelope_by_task):
        raise ContractValidationError("identity registry requires exactly one decision per model task")

    union_find = _UnionFind(node_by_key)
    for raw_edge in preparation.deterministic_edges:
        left = _string(raw_edge.get("left_node_key"), "deterministic left_node_key")
        right = _string(raw_edge.get("right_node_key"), "deterministic right_node_key")
        if left not in node_by_key or right not in node_by_key:
            raise ContractValidationError("deterministic identity edge references unknown node")
        union_find.union(left, right)

    decisions = list(grounded_decisions)
    decisions.sort(
        key=lambda item: (
            node_by_key[item.current_node_key].order_position,
            item.current_node_key,
            item.candidate_node_key,
        )
    )
    cannot_links: set[frozenset[str]] = {
        frozenset({item.current_node_key, item.candidate_node_key})
        for item in decisions
        if item.identity_relation == "different_characters"
    }
    decisions_by_current: dict[str, list[GroundedIdentityDecision]] = {}
    for decision in decisions:
        decisions_by_current.setdefault(decision.current_node_key, []).append(decision)

    accepted_roles: dict[str, str] = {}
    unresolved_reasons: dict[str, tuple[str, tuple[GroundedIdentityDecision, ...]]] = {}
    extra_review: list[tuple[str, str, tuple[GroundedIdentityDecision, ...]]] = []
    for current in nodes:
        current_decisions = decisions_by_current.get(current.node_key, [])
        same = [item for item in current_decisions if item.identity_relation == "same_character"]
        uncertain = [item for item in current_decisions if item.identity_relation == "uncertain"]
        target_roots: dict[str, list[GroundedIdentityDecision]] = {}
        for decision in same:
            target_roots.setdefault(union_find.find(decision.candidate_node_key), []).append(decision)
        if len(target_roots) > 1:
            value = ("multiple_same_character_candidates", tuple(same))
            unresolved_reasons[current.node_key] = value
            extra_review.append((current.node_key, value[0], value[1]))
            continue
        if len(target_roots) == 1:
            selected = min(
                next(iter(target_roots.values())),
                key=lambda item: (item.candidate_node_key, item.task_cache_key),
            )
            if _clusters_have_cannot_link(
                union_find,
                current.node_key,
                selected.candidate_node_key,
                cannot_links,
            ):
                value = ("cannot_link_constraint", (selected,))
                unresolved_reasons[current.node_key] = value
                extra_review.append((current.node_key, value[0], value[1]))
                continue
            union_find.union(current.node_key, selected.candidate_node_key)
            if selected.label_relation is not None:
                accepted_roles[current.node_key] = selected.label_relation
            if any(item.issues for item in same):
                extra_review.append((current.node_key, "partial_identity_evidence_grounding", tuple(same)))
            continue
        if uncertain:
            review_type = (
                "identity_evidence_not_grounded"
                if any(item.requested_identity_relation != "uncertain" for item in uncertain)
                else "insufficient_identity_evidence"
            )
            unresolved_reasons[current.node_key] = (review_type, tuple(uncertain))
            extra_review.append((current.node_key, review_type, tuple(uncertain)))

    components: dict[str, list[LocalCharacterNode]] = {}
    for node in nodes:
        components.setdefault(union_find.find(node.node_key), []).append(node)
    unresolved_nodes = {
        node_key
        for node_key in unresolved_reasons
        if len(components[union_find.find(node_key)]) == 1
    }

    characters: list[dict[str, object]] = []
    node_to_character: dict[str, str] = {}
    for members in components.values():
        if len(members) == 1 and members[0].node_key in unresolved_nodes:
            continue
        members.sort(key=lambda item: (item.order_position, item.node_key))
        character_id = _character_id(preparation.local_nodes.source_document_version_id, members)
        canonical = _canonical_node(members)
        for member in members:
            node_to_character[member.node_key] = character_id
        labels_by_quote: dict[str, str] = {}
        role_rank = {
            "name": 0,
            "name_variant": 1,
            "alias": 2,
            "title": 3,
            "contextual_description": 4,
            "unknown": 5,
        }
        for member in members:
            role = _label_role(member, canonical, accepted_roles)
            old = labels_by_quote.get(member.label_quote)
            if old is None or role_rank[role] < role_rank[old]:
                labels_by_quote[member.label_quote] = role
        fact_by_hash: dict[str, IdentityAppearanceFactRef] = {}
        for member in members:
            for fact in member.appearance_fact_refs:
                fact_by_hash[fact.fact_hash] = fact
        fact_refs = sorted(fact_by_hash.values(), key=lambda item: (item.document_fact_span, item.fact_hash))
        characters.append(
            {
                "character_id": character_id,
                "identity_status": "linked" if len(members) > 1 else "singleton",
                "canonical_label": canonical.label_quote,
                "canonical_label_status": (
                    "confirmed_name_like" if canonical.label_type == "exact" else "provisional_description"
                ),
                "labels": [
                    {
                        "label_quote": label,
                        "label_role": role,
                        "globally_unique": False,
                    }
                    for label, role in sorted(labels_by_quote.items(), key=lambda item: (role_rank[item[1]], item[0]))
                ],
                "member_character_refs": [_wrapped_ref(member) for member in members],
                "appearance_fact_refs": [
                    {"fact_hash": fact.fact_hash, "fact_quote": fact.fact_quote} for fact in fact_refs
                ],
                "possible_conflicts": _possible_conflicts(character_id, fact_refs),
            }
        )
    characters.sort(key=lambda item: str(item["character_id"]))

    label_owners: dict[str, set[str]] = {}
    for character in characters:
        for label in _sequence(character["labels"], "character labels"):
            label_mapping = _mapping(label, "character label")
            label_owners.setdefault(_string(label_mapping["label_quote"], "label_quote"), set()).add(
                _string(character["character_id"], "character_id")
            )
    for character in characters:
        for raw_label in _sequence(character["labels"], "character labels"):
            label = _mapping(raw_label, "character label")
            role = _string(label["label_role"], "label_role")
            quote = _string(label["label_quote"], "label_quote")
            label["globally_unique"] = (
                role not in {"title", "contextual_description", "unknown"}
                and len(label_owners[quote]) == 1
            )

    review_items: list[dict[str, object]] = []
    unresolved_bindings: list[dict[str, object]] = []
    recorded_reviews: set[str] = set()
    for node_key, review_type, related in extra_review:
        node = node_by_key[node_key]
        candidate_keys = tuple(item.candidate_node_key for item in related)
        review_id = _review_id(node_key, review_type, candidate_keys)
        if review_id in recorded_reviews:
            continue
        recorded_reviews.add(review_id)
        candidate_ids = sorted(
            {
                node_to_character[key]
                for key in candidate_keys
                if key in node_to_character
            }
        )
        evidence = [
            item.to_dict()
            for decision in related
            for item in decision.grounded_identity_evidence
        ]
        issue_codes = sorted({issue.code for decision in related for issue in decision.issues})
        review_items.append(
            {
                "review_item_id": review_id,
                "review_type": review_type,
                "subject_character_ref": _wrapped_ref(node),
                "label_quote": node.label_quote,
                "candidate_character_ids": candidate_ids,
                "grounded_identity_evidence": evidence,
                "issue_codes": issue_codes,
                "status": "pending",
            }
        )
        if node_key in unresolved_nodes:
            unresolved_bindings.append(
                {
                    "source_character_ref": _wrapped_ref(node),
                    "label_quote": node.label_quote,
                    "candidate_character_ids": candidate_ids,
                    "reason_code": review_type,
                    "review_item_id": review_id,
                }
            )
    review_items.sort(key=lambda item: str(item["review_item_id"]))
    unresolved_bindings.sort(key=lambda item: str(item["review_item_id"]))

    cannot_link_constraints = []
    for pair in sorted(cannot_links, key=lambda item: sorted(item)):
        left, right = sorted(pair)
        decision = next(
            item
            for item in decisions
            if item.identity_relation == "different_characters"
            and frozenset({item.current_node_key, item.candidate_node_key}) == pair
        )
        cannot_link_constraints.append(
            {
                "left_node_key": left,
                "right_node_key": right,
                "left_character_id": node_to_character.get(left),
                "right_character_id": node_to_character.get(right),
                "grounded_identity_evidence": [
                    item.to_dict() for item in decision.grounded_identity_evidence
                ],
            }
        )

    return {
        "schema_version": IDENTITY_REGISTRY_VERSION,
        "identity_policy_version": IDENTITY_POLICY_VERSION,
        "candidate_policy_version": preparation.candidate_policy_version,
        "conflict_policy_version": IDENTITY_CONFLICT_POLICY_VERSION,
        "source_document_version_id": preparation.local_nodes.source_document_version_id,
        "document_hash": preparation.local_nodes.document_hash,
        "characters": characters,
        "unresolved_bindings": unresolved_bindings,
        "review_items": review_items,
        "cannot_link_constraints": cannot_link_constraints,
        "summary": {
            "local_character_nodes": len(nodes),
            "bound_local_nodes": len(node_to_character),
            "global_characters": len(characters),
            "linked_characters": sum(item["identity_status"] == "linked" for item in characters),
            "singleton_characters": sum(item["identity_status"] == "singleton" for item in characters),
            "unresolved_bindings": len(unresolved_bindings),
            "review_items": len(review_items),
            "cannot_link_constraints": len(cannot_link_constraints),
            "appearance_fact_refs": sum(len(item["appearance_fact_refs"]) for item in characters),
            "possible_conflicts": sum(len(item["possible_conflicts"]) for item in characters),
        },
    }
