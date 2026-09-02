from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Mapping, Sequence

from .errors import ContractValidationError
from .identity import (
    IDENTITY_RELATIONS,
    LABEL_RELATIONS,
    GroundedIdentityDecision,
    GroundedIdentityEvidence,
    IdentityGroundingIssue,
    IdentityPreparation,
    IdentityProvider,
    IdentityProviderRequest,
    LocalCharacterNode,
    _bridge_context,
    build_identity_preparation,
)
from .text import SourceSpan, find_safe_quote_matches, sha256_text

CLUSTER_RESCUE_ENVELOPE_VERSION = "m3-cluster-rescue-envelope-v1"
CLUSTER_RESCUE_DECISION_VERSION = "grounded-cluster-rescue-decision-v1"
CLUSTER_RESCUE_POLICY_VERSION = "residual-cluster-adjudication-v2"
CLUSTER_RELATION_CONTEXT_VERSION = "candidate-specific-relationship-context-v1"

CLUSTER_RESCUE_SYSTEM_INSTRUCTION = """
你只处理代码筛选出的跨 Chunk 人物身份疑难项。

输入包含一个 current_character 和少量 candidate_characters。每个候选使用本次任务内的
candidate_number 标识；它不是系统人物 ID。

严格遵守：
1. current/candidate 的 context_quotes 和 appearance_fact_quotes 只帮助理解人物，不能作为最终身份证据。
2. identity_evidence_quotes 只能从你所选择候选的 relationship_context_quotes 中连续逐字复制；不得改写、概括、拼接，也不得引用其他候选的关系上下文。
3. same_character 必须有明确原文把两种称谓、两个阶段或两个描述连接为同一人物。仅同名、相似外貌、相同职业、位置接近或分别出现名字都不够。
4. different_characters 必须有明确原文区分所选的两个人物。仅年龄、衣着或外貌不同不够，因为人物可能成长、换装、受伤或伪装。
5. 没有足够关系原文时返回 uncertain；不要使用作品常识或外部知识。
6. same_character 才输出 label_relation；different_characters 和 uncertain 必须为 null。
7. 不输出 ref、人物 ID、span、hash、置信度、解释或 Schema 外字段。
"""


def _canonical_hash(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(payload.encode("utf-8")).hexdigest()


def _string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractValidationError(f"{label} must be a non-empty string")
    return value


def _sequence(value: object, label: str) -> Sequence[object]:
    if not isinstance(value, list):
        raise ContractValidationError(f"{label} must be an array")
    return value


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ContractValidationError(f"{label} must be an object")
    return value


def cluster_rescue_response_schema(candidate_count: int) -> dict[str, Any]:
    if candidate_count < 1:
        raise ContractValidationError("cluster rescue requires at least one candidate")
    candidate_numbers = list(range(1, candidate_count + 1))
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "identity_relation",
            "candidate_number",
            "label_relation",
            "identity_evidence_quotes",
        ],
        "properties": {
            "identity_relation": {"type": "string", "enum": list(IDENTITY_RELATIONS)},
            "candidate_number": {
                "anyOf": [{"type": "integer", "enum": candidate_numbers}, {"type": "null"}]
            },
            "label_relation": {
                "anyOf": [{"type": "string", "enum": list(LABEL_RELATIONS)}, {"type": "null"}]
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
                        "candidate_number": {"type": "integer", "enum": candidate_numbers},
                        "label_relation": {"type": "string", "enum": list(LABEL_RELATIONS)},
                        "identity_evidence_quotes": {"minItems": 1},
                    }
                },
            },
            {
                "if": {"properties": {"identity_relation": {"const": "different_characters"}}},
                "then": {
                    "properties": {
                        "candidate_number": {"type": "integer", "enum": candidate_numbers},
                        "label_relation": {"type": "null"},
                        "identity_evidence_quotes": {"minItems": 1},
                    }
                },
            },
            {
                "if": {"properties": {"identity_relation": {"const": "uncertain"}}},
                "then": {
                    "properties": {
                        "candidate_number": {"type": "null"},
                        "label_relation": {"type": "null"},
                        "identity_evidence_quotes": {"maxItems": 0},
                    }
                },
            },
        ],
    }


@dataclass(frozen=True)
class ClusterCharacterModelInput:
    labels: tuple[str, ...]
    context_quotes: tuple[str, ...]
    appearance_fact_quotes: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "labels": list(self.labels),
            "context_quotes": list(self.context_quotes),
            "appearance_fact_quotes": list(self.appearance_fact_quotes),
        }


@dataclass(frozen=True)
class ClusterCandidateModelInput:
    candidate_number: int
    known_labels: tuple[str, ...]
    context_quotes: tuple[str, ...]
    appearance_fact_quotes: tuple[str, ...]
    relationship_context_quotes: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "candidate_number": self.candidate_number,
            "known_labels": list(self.known_labels),
            "context_quotes": list(self.context_quotes),
            "appearance_fact_quotes": list(self.appearance_fact_quotes),
            "relationship_context_quotes": list(self.relationship_context_quotes),
        }


@dataclass(frozen=True)
class ClusterRescueModelInput:
    current_character: ClusterCharacterModelInput
    candidate_characters: tuple[ClusterCandidateModelInput, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "current_character": self.current_character.to_dict(),
            "candidate_characters": [item.to_dict() for item in self.candidate_characters],
        }


@dataclass(frozen=True)
class ClusterRelationshipBinding:
    candidate_number: int
    context_quote: str
    document_span: SourceSpan

    def to_dict(self) -> dict[str, object]:
        return {
            "candidate_number": self.candidate_number,
            "context_quote": self.context_quote,
            "document_span": self.document_span.to_dict(),
        }


@dataclass(frozen=True)
class ClusterCandidateBinding:
    candidate_number: int
    candidate_character_id: str
    candidate_anchor_node_key: str
    candidate_reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "candidate_number": self.candidate_number,
            "candidate_character_id": self.candidate_character_id,
            "candidate_anchor_node_key": self.candidate_anchor_node_key,
            "candidate_reasons": list(self.candidate_reasons),
        }


@dataclass(frozen=True)
class ClusterRescueEnvelope:
    subject_character_id: str
    subject_anchor_node_key: str
    candidate_bindings: tuple[ClusterCandidateBinding, ...]
    relationship_bindings: tuple[ClusterRelationshipBinding, ...]
    task_cache_key: str
    model_input: ClusterRescueModelInput
    schema_version: str = CLUSTER_RESCUE_ENVELOPE_VERSION

    def __post_init__(self) -> None:
        expected_numbers = tuple(range(1, len(self.candidate_bindings) + 1))
        if tuple(item.candidate_number for item in self.candidate_bindings) != expected_numbers:
            raise ContractValidationError("cluster rescue candidate numbers must be contiguous")
        if tuple(item.candidate_number for item in self.model_input.candidate_characters) != expected_numbers:
            raise ContractValidationError("cluster rescue model candidates do not match bindings")
        valid_numbers = set(expected_numbers)
        if not self.relationship_bindings or any(
            item.candidate_number not in valid_numbers for item in self.relationship_bindings
        ):
            raise ContractValidationError("cluster rescue relationship bindings are invalid")
        expected = _canonical_hash(
            {
                "schema_version": self.schema_version,
                "policy_version": CLUSTER_RESCUE_POLICY_VERSION,
                "context_version": CLUSTER_RELATION_CONTEXT_VERSION,
                "subject_character_id": self.subject_character_id,
                "subject_anchor_node_key": self.subject_anchor_node_key,
                "candidate_bindings": [item.to_dict() for item in self.candidate_bindings],
                "model_input": self.model_input.to_dict(),
            }
        )
        if self.task_cache_key != expected:
            raise ContractValidationError("cluster rescue task_cache_key does not match envelope")

    def model_payload(self) -> dict[str, object]:
        return self.model_input.to_dict()

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "policy_version": CLUSTER_RESCUE_POLICY_VERSION,
            "context_version": CLUSTER_RELATION_CONTEXT_VERSION,
            "subject_character_id": self.subject_character_id,
            "subject_anchor_node_key": self.subject_anchor_node_key,
            "candidate_bindings": [item.to_dict() for item in self.candidate_bindings],
            "relationship_bindings": [item.to_dict() for item in self.relationship_bindings],
            "task_cache_key": self.task_cache_key,
            "model_input": self.model_input.to_dict(),
        }


@dataclass(frozen=True)
class ClusterRescuePreparation:
    baseline_registry: Mapping[str, object]
    envelopes: tuple[ClusterRescueEnvelope, ...]

    def summary(self) -> dict[str, object]:
        return {
            "schema_version": "cluster-rescue-preparation-summary-v1",
            "policy_version": CLUSTER_RESCUE_POLICY_VERSION,
            "planned_tasks": len(self.envelopes),
            "candidate_options": sum(len(item.candidate_bindings) for item in self.envelopes),
            "relationship_context_quotes": sum(
                len(item.relationship_bindings) for item in self.envelopes
            ),
            "provider_calls": 0,
        }


@dataclass(frozen=True)
class ClusterRescueModelOutput:
    identity_relation: str
    candidate_number: int | None
    label_relation: str | None
    identity_evidence_quotes: tuple[str, ...]

    @classmethod
    def parse(cls, raw: str | Mapping[str, Any], *, candidate_count: int) -> ClusterRescueModelOutput:
        if isinstance(raw, str):
            try:
                value = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ContractValidationError("cluster rescue model output is invalid JSON") from exc
        else:
            value = raw
        parsed = _mapping(value, "cluster rescue model output")
        expected = {
            "identity_relation",
            "candidate_number",
            "label_relation",
            "identity_evidence_quotes",
        }
        if set(parsed) != expected:
            raise ContractValidationError("cluster rescue model output fields mismatch")
        relation = _string(parsed["identity_relation"], "identity_relation")
        if relation not in IDENTITY_RELATIONS:
            raise ContractValidationError("cluster rescue identity_relation is invalid")
        number = parsed["candidate_number"]
        if number is not None and (isinstance(number, bool) or not isinstance(number, int)):
            raise ContractValidationError("cluster rescue candidate_number must be integer or null")
        if number is not None and not 1 <= number <= candidate_count:
            raise ContractValidationError("cluster rescue candidate_number is outside the task")
        label_relation = parsed["label_relation"]
        if label_relation is not None:
            label_relation = _string(label_relation, "label_relation")
            if label_relation not in LABEL_RELATIONS:
                raise ContractValidationError("cluster rescue label_relation is invalid")
        raw_quotes = _sequence(parsed["identity_evidence_quotes"], "identity_evidence_quotes")
        quotes = tuple(_string(item, f"identity_evidence_quotes[{index}]") for index, item in enumerate(raw_quotes))
        if len(quotes) != len(set(quotes)):
            raise ContractValidationError("cluster rescue identity evidence must be unique")
        if relation == "same_character":
            if number is None or label_relation is None or not quotes:
                raise ContractValidationError("cluster same_character requires candidate, label relation and evidence")
        elif relation == "different_characters":
            if number is None or label_relation is not None or not quotes:
                raise ContractValidationError("cluster different_characters requires candidate and evidence")
        elif number is not None or label_relation is not None or quotes:
            raise ContractValidationError("cluster uncertain requires null candidate/label and no evidence")
        return cls(relation, number, label_relation, quotes)

    def to_dict(self) -> dict[str, object]:
        return {
            "identity_relation": self.identity_relation,
            "candidate_number": self.candidate_number,
            "label_relation": self.label_relation,
            "identity_evidence_quotes": list(self.identity_evidence_quotes),
        }


@dataclass(frozen=True)
class GroundedClusterRescueDecision:
    subject_character_id: str
    subject_anchor_node_key: str
    selected_candidate_number: int | None
    selected_candidate_character_id: str | None
    selected_candidate_anchor_node_key: str | None
    task_cache_key: str
    requested_identity_relation: str
    identity_relation: str
    label_relation: str | None
    grounded_identity_evidence: tuple[GroundedIdentityEvidence, ...]
    issues: tuple[IdentityGroundingIssue, ...]
    schema_version: str = CLUSTER_RESCUE_DECISION_VERSION

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "subject_character_id": self.subject_character_id,
            "subject_anchor_node_key": self.subject_anchor_node_key,
            "selected_candidate_number": self.selected_candidate_number,
            "selected_candidate_character_id": self.selected_candidate_character_id,
            "selected_candidate_anchor_node_key": self.selected_candidate_anchor_node_key,
            "task_cache_key": self.task_cache_key,
            "requested_identity_relation": self.requested_identity_relation,
            "identity_relation": self.identity_relation,
            "label_relation": self.label_relation,
            "grounded_identity_evidence": [item.to_dict() for item in self.grounded_identity_evidence],
            "issues": [item.to_dict() for item in self.issues],
        }

    def to_supplemental_decision(self) -> GroundedIdentityDecision | None:
        if self.selected_candidate_anchor_node_key is None:
            return None
        return GroundedIdentityDecision(
            current_node_key=self.subject_anchor_node_key,
            candidate_node_key=self.selected_candidate_anchor_node_key,
            task_cache_key="cluster-rescue-" + self.task_cache_key,
            requested_identity_relation=self.requested_identity_relation,
            identity_relation=self.identity_relation,
            label_relation=self.label_relation,
            grounded_identity_evidence=self.grounded_identity_evidence,
            issues=self.issues,
        )


def _wrapped_ref_identity(value: Mapping[str, object]) -> str:
    ref_type = _string(value.get("ref_type"), "member ref_type")
    ref = _mapping(value.get(f"{ref_type}_character_ref"), "member character ref")
    return json.dumps(
        {"ref_type": ref_type, "source_character_ref": ref},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _node_ref_identity(node: LocalCharacterNode) -> str:
    return json.dumps(
        {"ref_type": node.ref_type, "source_character_ref": node.source_character_ref},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _select_context_quotes(members: Sequence[LocalCharacterNode], limit: int) -> tuple[str, ...]:
    contexts = sorted(
        {
            (binding.document_span.start, binding.document_span.end, binding.context_quote)
            for member in members
            for binding in member.context_bindings
        }
    )
    if len(contexts) > limit:
        if limit == 1:
            contexts = [contexts[0]]
        else:
            indices = sorted({round(index * (len(contexts) - 1) / (limit - 1)) for index in range(limit)})
            contexts = [contexts[index] for index in indices]
    return tuple(item[2] for item in contexts)


def _relationship_bindings(
    subject_members: Sequence[LocalCharacterNode],
    candidate_members: Sequence[LocalCharacterNode],
    *,
    candidate_number: int,
    document_text: str,
    max_characters: int,
    max_contexts: int,
) -> tuple[ClusterRelationshipBinding, ...]:
    pairs = sorted(
        (
            (abs(left.order_position - right.order_position), left, right)
            for left in subject_members
            for right in candidate_members
        ),
        key=lambda item: (item[0], item[1].order_position, item[2].order_position),
    )
    result: list[ClusterRelationshipBinding] = []
    seen: set[tuple[int, int, str]] = set()
    for _, left, right in pairs:
        for binding in _bridge_context(left, right, document_text, max_characters):
            key = (binding.document_span.start, binding.document_span.end, binding.context_quote)
            if key in seen:
                continue
            seen.add(key)
            result.append(
                ClusterRelationshipBinding(
                    candidate_number,
                    binding.context_quote,
                    binding.document_span,
                )
            )
    subject_labels = {member.label_quote for member in subject_members}
    candidate_labels = {member.label_quote for member in candidate_members}
    identity_markers = ("我叫", "名叫", "叫做", "称为", "称作", "这位是", "就是", "正是")

    def directly_connects(binding: ClusterRelationshipBinding) -> bool:
        subject_hit = any(label in binding.context_quote for label in subject_labels)
        candidate_hit = any(label in binding.context_quote for label in candidate_labels)
        if not subject_hit or not candidate_hit:
            return False
        shared_labels = subject_labels & candidate_labels
        if not shared_labels:
            return True
        distinct_subject_hit = any(
            label in binding.context_quote for label in subject_labels - shared_labels
        )
        distinct_candidate_hit = any(
            label in binding.context_quote for label in candidate_labels - shared_labels
        )
        if distinct_subject_hit or distinct_candidate_hit:
            return True
        repeated_shared_label = any(binding.context_quote.count(label) >= 2 for label in shared_labels)
        explicit_identity_marker = any(marker in binding.context_quote for marker in identity_markers)
        return repeated_shared_label or explicit_identity_marker

    direct = [item for item in result if directly_connects(item)]
    candidates = direct
    candidates.sort(
        key=lambda item: (
            0 if any(marker in item.context_quote for marker in identity_markers) else 1,
            item.document_span.end - item.document_span.start,
            item.document_span.start,
        )
    )
    return tuple(candidates[:max_contexts])


def build_cluster_rescue_preparation(
    *,
    preparation: IdentityPreparation,
    grounded_decisions: Sequence[GroundedIdentityDecision],
    baseline_registry: Mapping[str, object],
    document_text: str,
    max_candidates_per_task: int = 3,
    max_contexts_per_character: int = 4,
    max_relationship_contexts_per_candidate: int = 3,
    max_relationship_context_characters: int = 1200,
) -> ClusterRescuePreparation:
    if sha256_text(document_text) != preparation.local_nodes.document_hash:
        raise ContractValidationError("cluster rescue document hash mismatch")
    if max_candidates_per_task < 1 or max_contexts_per_character < 1:
        raise ContractValidationError("cluster rescue limits must be positive")
    if max_relationship_contexts_per_candidate < 1 or max_relationship_context_characters < 1:
        raise ContractValidationError("cluster rescue relationship limits must be positive")

    nodes = preparation.local_nodes.nodes
    node_by_key = {node.node_key: node for node in nodes}
    node_by_ref = {_node_ref_identity(node): node for node in nodes}
    character_members: dict[str, tuple[LocalCharacterNode, ...]] = {}
    character_data: dict[str, Mapping[str, object]] = {}
    node_to_character: dict[str, str] = {}
    for raw_character in _sequence(baseline_registry.get("characters"), "baseline characters"):
        character = _mapping(raw_character, "baseline character")
        character_id = _string(character.get("character_id"), "baseline character_id")
        members: list[LocalCharacterNode] = []
        for raw_ref in _sequence(character.get("member_character_refs"), "member_character_refs"):
            identity = _wrapped_ref_identity(_mapping(raw_ref, "member_character_ref"))
            node = node_by_ref.get(identity)
            if node is None:
                raise ContractValidationError("baseline registry member does not exist in local nodes")
            members.append(node)
            node_to_character[node.node_key] = character_id
        members.sort(key=lambda item: (item.order_position, item.node_key))
        character_members[character_id] = tuple(members)
        character_data[character_id] = character
    if set(node_to_character) != set(node_by_key):
        raise ContractValidationError("cluster rescue requires every local node in the baseline registry")

    cannot_character_pairs = {
        frozenset({str(item.get("left_character_id")), str(item.get("right_character_id"))})
        for raw in _sequence(baseline_registry.get("cannot_link_constraints"), "cannot_link_constraints")
        for item in [_mapping(raw, "cannot_link_constraint")]
        if item.get("left_character_id") is not None and item.get("right_character_id") is not None
    }
    proposals: dict[tuple[str, str], tuple[int, set[str]]] = {}

    def cluster_order_key(character_id: str) -> tuple[int, tuple[str, ...], str]:
        members = character_members[character_id]
        return (
            members[0].order_position,
            tuple(sorted(member.node_key for member in members)),
            character_id,
        )

    def propose(subject_id: str, candidate_id: str, score: int, reason: str) -> None:
        if subject_id == candidate_id or frozenset({subject_id, candidate_id}) in cannot_character_pairs:
            return
        if cluster_order_key(candidate_id) < cluster_order_key(subject_id):
            subject_id, candidate_id = candidate_id, subject_id
        key = (subject_id, candidate_id)
        old_score, reasons = proposals.get(key, (0, set()))
        reasons.add(reason)
        proposals[key] = (max(old_score, score), reasons)

    for raw in _sequence(baseline_registry.get("unresolved_bindings"), "unresolved_bindings"):
        unresolved = _mapping(raw, "unresolved_binding")
        subject_node = node_by_ref.get(
            _wrapped_ref_identity(_mapping(unresolved.get("source_character_ref"), "unresolved source ref"))
        )
        if subject_node is None:
            raise ContractValidationError("unresolved source ref is not a local node")
        subject_id = node_to_character[subject_node.node_key]
        for candidate_id in _sequence(unresolved.get("candidate_character_ids"), "candidate_character_ids"):
            propose(subject_id, _string(candidate_id, "candidate_character_id"), 120, "registry_unresolved")

    for decision in grounded_decisions:
        if decision.identity_relation != "uncertain":
            continue
        subject_id = node_to_character[decision.current_node_key]
        candidate_id = node_to_character[decision.candidate_node_key]
        propose(subject_id, candidate_id, 100, "base_pair_uncertain")

    refreshed = build_identity_preparation(
        local_nodes=preparation.local_nodes,
        document_text=document_text,
        max_candidates_per_node=2,
        max_bridge_characters=max_relationship_context_characters,
    )
    existing_pairs = {
        (item.current_node_key, item.candidate_node_key) for item in preparation.envelopes
    }
    for envelope in refreshed.envelopes:
        pair = (envelope.current_node_key, envelope.candidate_node_key)
        if pair in existing_pairs:
            continue
        if "nearby_explicit_identity_bridge" not in envelope.candidate_reasons:
            continue
        propose(
            node_to_character[envelope.current_node_key],
            node_to_character[envelope.candidate_node_key],
            115,
            "new_explicit_identity_bridge",
        )

    grouped: dict[str, list[tuple[int, str, set[str]]]] = {}
    for (subject_id, candidate_id), (score, reasons) in proposals.items():
        grouped.setdefault(subject_id, []).append((score, candidate_id, reasons))

    envelopes: list[ClusterRescueEnvelope] = []
    for subject_id, candidates in grouped.items():
        subject_members = character_members[subject_id]
        subject_anchor = subject_members[0]
        selected: list[
            tuple[str, tuple[str, ...], tuple[ClusterRelationshipBinding, ...]]
        ] = []
        candidates.sort(
            key=lambda item: (
                -item[0],
                character_members[item[1]][0].order_position,
                item[1],
            )
        )
        for _, candidate_id, reasons in candidates:
            provisional_number = len(selected) + 1
            relations = _relationship_bindings(
                subject_members,
                character_members[candidate_id],
                candidate_number=provisional_number,
                document_text=document_text,
                max_characters=max_relationship_context_characters,
                max_contexts=max_relationship_contexts_per_candidate,
            )
            if not relations:
                continue
            selected.append((candidate_id, tuple(sorted(reasons)), relations))
            if len(selected) >= max_candidates_per_task:
                break
        if not selected:
            continue

        candidate_bindings: list[ClusterCandidateBinding] = []
        relationship_bindings: list[ClusterRelationshipBinding] = []
        candidate_inputs: list[ClusterCandidateModelInput] = []
        for number, (candidate_id, reasons, raw_relations) in enumerate(selected, start=1):
            candidate_members = character_members[candidate_id]
            relations = tuple(
                ClusterRelationshipBinding(number, item.context_quote, item.document_span)
                for item in raw_relations
            )
            relationship_bindings.extend(relations)
            candidate = character_data[candidate_id]
            labels = tuple(
                dict.fromkeys(
                    _string(_mapping(item, "candidate label").get("label_quote"), "label_quote")
                    for item in _sequence(candidate.get("labels"), "candidate labels")
                )
            )
            facts = tuple(
                dict.fromkeys(fact.fact_quote for member in candidate_members for fact in member.appearance_fact_refs)
            )
            candidate_bindings.append(
                ClusterCandidateBinding(
                    number,
                    candidate_id,
                    candidate_members[0].node_key,
                    reasons,
                )
            )
            candidate_inputs.append(
                ClusterCandidateModelInput(
                    number,
                    labels,
                    _select_context_quotes(candidate_members, max_contexts_per_character),
                    facts,
                    tuple(item.context_quote for item in relations),
                )
            )

        subject = character_data[subject_id]
        subject_labels = tuple(
            dict.fromkeys(
                _string(_mapping(item, "subject label").get("label_quote"), "label_quote")
                for item in _sequence(subject.get("labels"), "subject labels")
            )
        )
        subject_facts = tuple(
            dict.fromkeys(fact.fact_quote for member in subject_members for fact in member.appearance_fact_refs)
        )
        model_input = ClusterRescueModelInput(
            ClusterCharacterModelInput(
                subject_labels,
                _select_context_quotes(subject_members, max_contexts_per_character),
                subject_facts,
            ),
            tuple(candidate_inputs),
        )
        hash_input = {
            "schema_version": CLUSTER_RESCUE_ENVELOPE_VERSION,
            "policy_version": CLUSTER_RESCUE_POLICY_VERSION,
            "context_version": CLUSTER_RELATION_CONTEXT_VERSION,
            "subject_character_id": subject_id,
            "subject_anchor_node_key": subject_anchor.node_key,
            "candidate_bindings": [item.to_dict() for item in candidate_bindings],
            "model_input": model_input.to_dict(),
        }
        envelopes.append(
            ClusterRescueEnvelope(
                subject_id,
                subject_anchor.node_key,
                tuple(candidate_bindings),
                tuple(relationship_bindings),
                _canonical_hash(hash_input),
                model_input,
            )
        )
    envelopes.sort(key=lambda item: (node_by_key[item.subject_anchor_node_key].order_position, item.task_cache_key))
    return ClusterRescuePreparation(baseline_registry, tuple(envelopes))


def ground_cluster_rescue_output(
    envelope: ClusterRescueEnvelope,
    output: ClusterRescueModelOutput,
    *,
    document_text: str,
) -> GroundedClusterRescueDecision:
    if output.identity_relation == "uncertain":
        return GroundedClusterRescueDecision(
            envelope.subject_character_id,
            envelope.subject_anchor_node_key,
            None,
            None,
            None,
            envelope.task_cache_key,
            "uncertain",
            "uncertain",
            None,
            (),
            (),
        )
    assert output.candidate_number is not None
    selected = envelope.candidate_bindings[output.candidate_number - 1]
    allowed_bindings = [
        item for item in envelope.relationship_bindings if item.candidate_number == output.candidate_number
    ]
    labels = set(envelope.model_input.current_character.labels)
    labels.update(envelope.model_input.candidate_characters[output.candidate_number - 1].known_labels)
    candidates_by_quote: dict[str, list[GroundedIdentityEvidence]] = {}
    issues: list[IdentityGroundingIssue] = []
    for binding in allowed_bindings:
        if binding.document_span.quote(document_text) != binding.context_quote:
            raise ContractValidationError("cluster relationship context no longer replays against document")
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
    for evidence_index, quote in enumerate(output.identity_evidence_quotes):
        candidates = candidates_by_quote.get(quote, [])
        compact = "".join(character for character in quote if not character.isspace())
        if compact in {"".join(character for character in label if not character.isspace()) for label in labels}:
            issues.append(
                IdentityGroundingIssue(
                    "identity_evidence_is_only_a_label",
                    evidence_index,
                    quote,
                    len(candidates),
                    "cluster rescue evidence cannot be only a character label",
                )
            )
            continue
        if len(compact) < 6:
            issues.append(
                IdentityGroundingIssue(
                    "identity_evidence_too_short",
                    evidence_index,
                    quote,
                    len(candidates),
                    "cluster rescue evidence is too short to support an identity relation",
                )
            )
            continue
        if len(candidates) == 1:
            grounded.append(candidates[0])
            continue
        issues.append(
            IdentityGroundingIssue(
                "ambiguous_cluster_identity_evidence" if candidates else "identity_evidence_not_in_relationship_context",
                evidence_index,
                quote,
                len(candidates),
                f"cluster identity evidence {quote!r} matched {len(candidates)} selected relationship occurrences",
            )
        )
    grounded.sort(key=lambda item: (item.document_span, item.evidence_quote))
    accepted = output.identity_relation if grounded else "uncertain"
    if not grounded:
        issues.append(
            IdentityGroundingIssue(
                "cluster_identity_relation_without_grounded_relationship_evidence",
                None,
                None,
                None,
                "cluster relation was downgraded because no selected relationship evidence grounded safely",
            )
        )
    return GroundedClusterRescueDecision(
        envelope.subject_character_id,
        envelope.subject_anchor_node_key,
        output.candidate_number,
        selected.candidate_character_id,
        selected.candidate_anchor_node_key,
        envelope.task_cache_key,
        output.identity_relation,
        accepted,
        output.label_relation if accepted == "same_character" else None,
        tuple(grounded),
        tuple(issues),
    )


class ClusterIdentityRescueOrchestrator:
    def __init__(self, provider: IdentityProvider) -> None:
        self._provider = provider

    def run(
        self,
        envelope: ClusterRescueEnvelope,
        *,
        document_text: str,
    ) -> GroundedClusterRescueDecision:
        request = IdentityProviderRequest(
            system_instruction=CLUSTER_RESCUE_SYSTEM_INSTRUCTION,
            user_payload=copy.deepcopy(envelope.model_payload()),
            response_schema=cluster_rescue_response_schema(len(envelope.candidate_bindings)),
            response_schema_name="m3_cluster_identity_rescue",
        )
        output = ClusterRescueModelOutput.parse(
            self._provider.generate(request),
            candidate_count=len(envelope.candidate_bindings),
        )
        return ground_cluster_rescue_output(envelope, output, document_text=document_text)
