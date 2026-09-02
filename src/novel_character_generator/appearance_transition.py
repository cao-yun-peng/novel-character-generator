from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from typing import Any, Mapping, Protocol, Sequence, runtime_checkable

from .errors import ContractValidationError
from .text import SourceSpan, find_safe_quote_matches, sha256_text

APPEARANCE_TRANSITION_CHUNKS_VERSION = "appearance-transition-chunks-v1"
DOCUMENT_APPEARANCE_STATES_VERSION = "document-character-appearance-states-v3"
APPEARANCE_TRANSITION_POLICY_VERSION = "full-coverage-roster-grounding-v3"
TRANSITION_DIMENSIONS = ("life", "form", "scene", "appearance")
STATE_ATTRIBUTES = {
    "life": "life_stage",
    "form": "form_state",
    "scene": "scene_state",
}
FORM_ANATOMY_EVIDENCE_MARKERS = (
    "附体",
    "变身",
    "身体",
    "全身",
    "头发",
    "眼睛",
    "皮肤",
    "毛发",
    "四肢",
    "手臂",
    "双手",
    "体型",
    "肌肉",
    "骨骼",
    "面容",
    "身高",
    "膨胀",
)
DIRECT_FORM_CHANGE_MARKERS = ("化为", "变成", "变作")
DIRECT_FORM_SUBJECTS = ("他", "她", "其", "整个人")
FORM_EXIT_MARKERS = ("收回", "解除", "退出", "结束", "消失", "褪去")
STATE_MATCH_IGNORABLE = frozenset(" \t，。、“”‘’；：！？…—")

APPEARANCE_TRANSITION_SYSTEM_INSTRUCTION = """
你只发现输入原文窗口中已经发生或明确正在发生的人物外貌状态转变。

规则：
1. characters 是上游身份层已确认的人物。事件主体 character 必须逐字选择其中的 name；不要重新识别人名、创建人物或输出 alias。
2. 扫描完整 text，不依赖关键词。识别 life（生命阶段）、form（形态/附体/变身）、scene（场景状态或装束状态）以及 appearance（具体外貌属性）转变。
3. 只输出原文明确支持的转变；静态外貌、情绪变化、动作和身份关系不是转变。
4. evidence 必须是 text 中一个连续、最小且完整的逐字片段；绝对不能把两个句子或段落删节后拼成一条 evidence。变化依据分散且无法用一个连续片段覆盖时不要输出。
5. before/after 是变化前后的“状态”，必须直接复制 evidence 中的连续短语，不得归纳或改写。解除、退出、收回某形态但原文没有明确说恢复成什么时，after 必须为空字符串。
6. form 只表示人物身体本身发生形态变化。武器、植物、衣物、光环或武魂的单纯出现、收回、持有和使用不是人物 form；武魂附体明确改变身体时才是 form。
7. life/form/scene 的 attribute 必须分别为 life_stage/form_state/scene_state；appearance 使用简短的具体属性名。
8. 未明说的一侧用空字符串。before/after 不能同时为空，也不能相同。
9. 不输出解释、置信度、ID、ref、span、hash、窗口信息或 schema 之外字段。没有事件时返回空 events。

必须覆盖的明确转变边界：
- “眼前的这个孩子，正是当初的某人”属于 life；可令 before 为空，after 复制“眼前的这个孩子”。
- “独狼，附体”属于 form 进入；即使后文另行描述毛发、眼睛，也要同时输出这个总形态事件。
- “收回了自己的武魂附体”属于 form 退出；before 复制“武魂附体”，after 为空。
- “换上/穿了一身新衣服”属于 scene 进入；仅仅“身穿灰衣”这类无更换动作的静态描写不属于转变。
"""


def transition_response_schema(character_names: Sequence[str]) -> dict[str, Any]:
    names = list(dict.fromkeys(character_names))
    if not names or any(not isinstance(name, str) or not name.strip() for name in names):
        raise ContractValidationError("transition response schema needs canonical character names")
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["events"],
        "properties": {
            "events": {
                "type": "array",
                "maxItems": 16,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "character",
                        "evidence",
                        "dimension",
                        "attribute",
                        "before",
                        "after",
                    ],
                    "properties": {
                        "character": {"type": "string", "enum": names},
                        "evidence": {"type": "string", "minLength": 1, "maxLength": 800},
                        "dimension": {"type": "string", "enum": list(TRANSITION_DIMENSIONS)},
                        "attribute": {"type": "string", "minLength": 1, "maxLength": 40},
                        "before": {"type": "string", "maxLength": 80},
                        "after": {"type": "string", "maxLength": 80},
                    },
                },
            }
        },
    }


@dataclass(frozen=True)
class AppearanceTransitionProviderRequest:
    system_instruction: str
    user_payload: Mapping[str, Any]
    response_schema: Mapping[str, Any]
    response_schema_name: str = "appearance_state_transitions"


@runtime_checkable
class AppearanceTransitionProvider(Protocol):
    def generate(
        self, request: AppearanceTransitionProviderRequest
    ) -> str | Mapping[str, Any]: ...


@dataclass(frozen=True)
class WindowCharacter:
    character_id: str
    name: str
    aliases: tuple[str, ...]

    def model_dict(self) -> dict[str, object]:
        return {"name": self.name, "aliases": list(self.aliases)}


@dataclass(frozen=True)
class AppearanceTransitionChunk:
    number: int
    chunk_id: str
    chunk_hash: str
    document_span: SourceSpan
    text: str
    characters: tuple[WindowCharacter, ...]

    def model_payload(self) -> dict[str, object]:
        return {
            "characters": [character.model_dict() for character in self.characters],
            "text": self.text,
        }

    def to_dict(self) -> dict[str, object]:
        return {
            "chunk_id": self.chunk_id,
            "chunk_hash": self.chunk_hash,
            "document_span": self.document_span.to_dict(),
            "characters": [character.model_dict() for character in self.characters],
            "text": self.text,
        }


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ContractValidationError(f"{label} must be an object")
    return value


def _sequence(value: object, label: str) -> Sequence[object]:
    if not isinstance(value, list):
        raise ContractValidationError(f"{label} must be an array")
    return value


def _string(value: object, label: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        suffix = "a string" if allow_empty else "a non-empty string"
        raise ContractValidationError(f"{label} must be {suffix}")
    return value


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ContractValidationError(f"{label} must be an integer")
    return value


def _span(value: object, label: str) -> SourceSpan:
    item = _mapping(value, label)
    if set(item) != {"start", "end"}:
        raise ContractValidationError(f"{label} must contain only start and end")
    return SourceSpan(_integer(item["start"], f"{label}.start"), _integer(item["end"], f"{label}.end"))


def _ref_key(ref_type: str, source_ref: Mapping[str, object]) -> str:
    return json.dumps(
        {"ref_type": ref_type, "source_character_ref": source_ref},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _member_ref_key(value: object, label: str) -> str:
    item = _mapping(value, label)
    ref_type = _string(item.get("ref_type"), f"{label}.ref_type")
    key = f"{ref_type}_character_ref"
    source_ref = _mapping(item.get(key), f"{label}.{key}")
    return _ref_key(ref_type, source_ref)


def _validate_document_identity(
    document_text: str,
    profiles: Mapping[str, object],
    local_nodes: Mapping[str, object],
    scopes: Mapping[str, object],
    chunk_manifest: Mapping[str, object],
) -> str:
    expected_hash = sha256_text(document_text)
    identities: list[str] = []
    for label, artifact in (
        ("profiles", profiles),
        ("local_nodes", local_nodes),
        ("chunk_manifest", chunk_manifest),
    ):
        if artifact.get("document_hash") != expected_hash:
            raise ContractValidationError(f"{label} document_hash does not match source text")
        identities.append(_string(artifact.get("source_document_version_id"), f"{label}.source_document_version_id"))
    identities.append(_string(scopes.get("source_document_version_id"), "scopes.source_document_version_id"))
    if len(set(identities)) != 1:
        raise ContractValidationError("transition source artifacts refer to different documents")
    if scopes.get("coverage_status") != "complete" or scopes.get("processed_source_end") != len(document_text):
        raise ContractValidationError("appearance scopes must completely cover source text")
    return identities[0]


def _intersects(left: SourceSpan, right: SourceSpan) -> bool:
    return left.start < right.end and right.start < left.end


def _source_chunks(
    document_text: str,
    chunk_manifest: Mapping[str, object],
) -> tuple[str, tuple[tuple[str, str, SourceSpan], ...]]:
    if chunk_manifest.get("schema_version") != "document-chunk-manifest-v3":
        raise ContractValidationError("unsupported source Chunk manifest version")
    if chunk_manifest.get("coverage_status") != "complete":
        raise ContractValidationError("source Chunk manifest must have complete coverage")
    if chunk_manifest.get("total_characters") != len(document_text):
        raise ContractValidationError("source Chunk manifest length does not match document")
    if chunk_manifest.get("processed_source_end") != len(document_text):
        raise ContractValidationError("source Chunk manifest does not reach document end")
    policy = _string(
        chunk_manifest.get("chunking_policy_version"),
        "chunk_manifest.chunking_policy_version",
    )
    chunks: list[tuple[str, str, SourceSpan]] = []
    for index, raw_chunk in enumerate(_sequence(chunk_manifest.get("chunks"), "chunk_manifest.chunks")):
        chunk = _mapping(raw_chunk, f"chunk_manifest.chunks[{index}]")
        chunk_id = _string(chunk.get("chunk_id"), "chunk.chunk_id")
        chunk_hash = _string(chunk.get("chunk_hash"), "chunk.chunk_hash")
        span = _span(chunk.get("chunk_source_span"), "chunk.chunk_source_span")
        if sha256_text(span.quote(document_text)) != chunk_hash:
            raise ContractValidationError("source Chunk hash does not replay from document")
        if chunks:
            previous = chunks[-1][2]
            if span.start <= previous.start or span.start > previous.end:
                raise ContractValidationError("source Chunks must increase with no coverage gap")
        elif span.start != 0:
            raise ContractValidationError("first source Chunk must start at zero")
        chunks.append((chunk_id, chunk_hash, span))
    if not chunks or chunks[-1][2].end != len(document_text):
        raise ContractValidationError("source Chunk list does not cover the document")
    if len({chunk_id for chunk_id, _, _ in chunks}) != len(chunks):
        raise ContractValidationError("source Chunk ids must be unique")
    return policy, tuple(chunks)


def build_appearance_transition_chunks(
    *,
    document_text: str,
    profiles: Mapping[str, object],
    local_nodes: Mapping[str, object],
    scopes: Mapping[str, object],
    chunk_manifest: Mapping[str, object],
) -> tuple[str, str, tuple[AppearanceTransitionChunk, ...]]:
    """Reuse original full-coverage Chunks and their already-bound local characters."""
    source_version = _validate_document_identity(
        document_text,
        profiles,
        local_nodes,
        scopes,
        chunk_manifest,
    )
    source_policy, source_chunks = _source_chunks(document_text, chunk_manifest)

    profile_items = _sequence(profiles.get("characters"), "profiles.characters")
    characters: dict[str, dict[str, object]] = {}
    ref_to_character: dict[str, str] = {}
    for index, raw_profile in enumerate(profile_items):
        profile = _mapping(raw_profile, f"profiles.characters[{index}]")
        character_id = _string(profile.get("character_id"), "profile.character_id")
        name = _string(profile.get("canonical_label"), "profile.canonical_label")
        if character_id in characters:
            raise ContractValidationError("duplicate profile character_id")
        if any(item["name"] == name for item in characters.values()):
            raise ContractValidationError("canonical character names must be unique for model selection")
        labels = {
            _string(_mapping(item, "profile.label").get("label_quote"), "profile.label.label_quote")
            for item in _sequence(profile.get("labels"), "profile.labels")
        }
        labels.discard(name)
        anchors: list[SourceSpan] = []
        for fact in _sequence(profile.get("appearance_facts"), "profile.appearance_facts"):
            fact_item = _mapping(fact, "profile.appearance_fact")
            anchors.append(_span(fact_item.get("document_fact_span"), "fact.document_fact_span"))
        characters[character_id] = {"name": name, "aliases": labels, "anchors": anchors}
        for member_index, member in enumerate(
            _sequence(profile.get("member_character_refs"), "profile.member_character_refs")
        ):
            key = _member_ref_key(member, f"profile.member_character_refs[{member_index}]")
            existing = ref_to_character.get(key)
            if existing is not None and existing != character_id:
                raise ContractValidationError("one local character ref belongs to multiple profiles")
            ref_to_character[key] = character_id

    chunk_characters: dict[str, set[str]] = {chunk_id: set() for chunk_id, _, _ in source_chunks}
    chunk_aliases: dict[tuple[str, str], set[str]] = {}
    chunk_spans = {chunk_id: span for chunk_id, _, span in source_chunks}
    for node_index, raw_node in enumerate(_sequence(local_nodes.get("nodes"), "local_nodes.nodes")):
        node = _mapping(raw_node, f"local_nodes.nodes[{node_index}]")
        ref_type = _string(node.get("ref_type"), "node.ref_type")
        source_ref = _mapping(node.get("source_character_ref"), "node.source_character_ref")
        character_id = ref_to_character.get(_ref_key(ref_type, source_ref))
        if character_id is None:
            continue
        chunk_id = _string(node.get("chunk_id"), "node.chunk_id")
        expected_span = chunk_spans.get(chunk_id)
        if expected_span is None:
            raise ContractValidationError("identity node references a Chunk outside the source manifest")
        node_chunk_span = _span(node.get("chunk_source_span"), "node.chunk_source_span")
        if node_chunk_span != expected_span:
            raise ContractValidationError("identity node Chunk span does not match source manifest")
        chunk_characters[chunk_id].add(character_id)
        character = characters[character_id]
        aliases = character["aliases"]
        anchors = character["anchors"]
        assert isinstance(aliases, set) and isinstance(anchors, list)
        label_quote = _string(node.get("label_quote"), "node.label_quote")
        if label_quote != character["name"]:
            aliases.add(label_quote)
            chunk_aliases.setdefault((chunk_id, character_id), set()).add(label_quote)
        for binding in _sequence(node.get("context_bindings"), "node.context_bindings"):
            item = _mapping(binding, "node.context_binding")
            anchors.append(_span(item.get("document_span"), "context_binding.document_span"))
        for fact in _sequence(node.get("appearance_fact_refs"), "node.appearance_fact_refs"):
            item = _mapping(fact, "node.appearance_fact_ref")
            anchors.append(_span(item.get("document_fact_span"), "fact_ref.document_fact_span"))

    windows: list[AppearanceTransitionChunk] = []
    for number, (chunk_id, chunk_hash, window_span) in enumerate(source_chunks, start=1):
        text = window_span.quote(document_text)
        roster: list[tuple[int, WindowCharacter]] = []
        for character_id in chunk_characters[chunk_id]:
            raw_character = characters[character_id]
            name = str(raw_character["name"])
            aliases = raw_character["aliases"]
            anchors = raw_character["anchors"]
            assert isinstance(aliases, set) and isinstance(anchors, list)
            direct_aliases = chunk_aliases.get((chunk_id, character_id), set())
            visible_labels = tuple(
                sorted(alias for alias in aliases if alias and (alias in text or alias in direct_aliases))
            )
            first_anchor = min(
                (anchor.start for anchor in anchors if _intersects(anchor, window_span)),
                default=len(document_text),
            )
            roster.append(
                (
                    first_anchor,
                    WindowCharacter(
                        character_id=character_id,
                        name=name,
                        aliases=visible_labels,
                    ),
                )
            )
        roster.sort(key=lambda item: (item[0], item[1].name, item[1].character_id))
        windows.append(
            AppearanceTransitionChunk(
                number=number,
                chunk_id=chunk_id,
                chunk_hash=chunk_hash,
                document_span=window_span,
                text=text,
                characters=tuple(item[1] for item in roster),
            )
        )

    return source_version, source_policy, tuple(windows)


def transition_chunks_artifact(
    *,
    source_document_version_id: str,
    windows: Sequence[AppearanceTransitionChunk],
    total_characters: int,
    source_chunking_policy_version: str,
) -> dict[str, object]:
    return {
        "schema_version": APPEARANCE_TRANSITION_CHUNKS_VERSION,
        "transition_policy_version": APPEARANCE_TRANSITION_POLICY_VERSION,
        "source_document_version_id": source_document_version_id,
        "total_characters": total_characters,
        "source_chunking_policy_version": source_chunking_policy_version,
        "chunks": [window.to_dict() for window in windows],
        "summary": {
            "planned_chunks": len(windows),
            "chunks_with_characters": sum(bool(window.characters) for window in windows),
            "model_calls": 0,
            "complete": True,
        },
    }


def parse_transition_model_output(
    raw_output: str | Mapping[str, Any], *, allowed_characters: Sequence[str]
) -> tuple[dict[str, str], ...]:
    if isinstance(raw_output, str):
        try:
            value = json.loads(raw_output)
        except json.JSONDecodeError as exc:
            raise ContractValidationError("transition Provider returned invalid JSON") from exc
    elif isinstance(raw_output, Mapping):
        value = dict(raw_output)
    else:
        raise ContractValidationError("transition Provider output must be JSON object or string")
    output = _mapping(value, "transition model output")
    if set(output) != {"events"}:
        raise ContractValidationError("transition model output must contain only events")
    allowed = set(allowed_characters)
    raw_events = _sequence(output["events"], "transition events")
    if len(raw_events) > 16:
        raise ContractValidationError("transition events exceed the per-Chunk limit")
    events: list[dict[str, str]] = []
    for index, raw_event in enumerate(raw_events):
        event = _mapping(raw_event, f"transition events[{index}]")
        expected = {"character", "evidence", "dimension", "attribute", "before", "after"}
        if set(event) != expected:
            raise ContractValidationError(f"transition event {index} fields mismatch")
        parsed = {
            "character": _string(event["character"], "event.character"),
            "evidence": _string(event["evidence"], "event.evidence"),
            "dimension": _string(event["dimension"], "event.dimension"),
            "attribute": _string(event["attribute"], "event.attribute"),
            "before": _string(event["before"], "event.before", allow_empty=True),
            "after": _string(event["after"], "event.after", allow_empty=True),
        }
        if parsed["character"] not in allowed:
            raise ContractValidationError("transition character is not in the window roster")
        if parsed["dimension"] not in TRANSITION_DIMENSIONS:
            raise ContractValidationError("transition dimension is invalid")
        if len(parsed["evidence"]) > 800 or len(parsed["attribute"]) > 40:
            raise ContractValidationError("transition evidence or attribute exceeds its limit")
        if len(parsed["before"]) > 80 or len(parsed["after"]) > 80:
            raise ContractValidationError("transition state exceeds its limit")
        required_attribute = STATE_ATTRIBUTES.get(parsed["dimension"])
        if required_attribute is not None and parsed["attribute"] != required_attribute:
            raise ContractValidationError("state transition attribute does not match dimension")
        if not parsed["before"] and not parsed["after"]:
            raise ContractValidationError("transition before and after cannot both be empty")
        if parsed["before"] == parsed["after"]:
            raise ContractValidationError("transition before and after cannot be equal")
        events.append(parsed)
    return tuple(events)


def _has_form_body_evidence(evidence: str, character: str, before: str, after: str) -> bool:
    state_text = before + after
    if any(marker in state_text for marker in FORM_ANATOMY_EVIDENCE_MARKERS):
        return True
    subjects = (character, *DIRECT_FORM_SUBJECTS)
    return any(
        f"{subject}{marker}" in evidence
        for subject in subjects
        for marker in DIRECT_FORM_CHANGE_MARKERS
    )


def _normalize_form_exit(
    *,
    evidence: str,
    before: str,
    after: str,
) -> tuple[str, str]:
    if before and after and any(marker in evidence and marker in after for marker in FORM_EXIT_MARKERS):
        return before, ""
    return before, after


def _state_phrase_matches(evidence: str, state: str) -> tuple[SourceSpan, ...]:
    if not state:
        return ()
    exact = tuple(match.span for match in find_safe_quote_matches(evidence, state))
    if exact:
        return exact
    compact_state = "".join(character for character in state if character not in STATE_MATCH_IGNORABLE)
    compact_evidence = [
        (character, index)
        for index, character in enumerate(evidence)
        if character not in STATE_MATCH_IGNORABLE
    ]
    if not compact_state or len(compact_state) > len(compact_evidence):
        return ()
    compact_text = "".join(character for character, _ in compact_evidence)
    spans: list[SourceSpan] = []
    offset = compact_text.find(compact_state)
    while offset >= 0:
        end_offset = offset + len(compact_state) - 1
        spans.append(SourceSpan(compact_evidence[offset][1], compact_evidence[end_offset][1] + 1))
        offset = compact_text.find(compact_state, offset + 1)
    return tuple(spans)


def _ground_states(evidence: str, before: str, after: str) -> tuple[str, str] | None:
    before_matches = _state_phrase_matches(evidence, before)
    after_matches = _state_phrase_matches(evidence, after)
    if before and len(before_matches) != 1:
        return None
    if after and len(after_matches) != 1:
        return None
    if before and after:
        if before_matches[0].end > after_matches[0].start:
            return None
    grounded_before = before_matches[0].quote(evidence) if before else ""
    grounded_after = after_matches[0].quote(evidence) if after else ""
    return grounded_before, grounded_after


def ground_transition_events(
    window: AppearanceTransitionChunk,
    events: Sequence[Mapping[str, str]],
) -> tuple[tuple[dict[str, object], ...], tuple[dict[str, object], ...]]:
    name_to_id = {character.name: character.character_id for character in window.characters}
    grounded: list[dict[str, object]] = []
    issues: list[dict[str, object]] = []
    for event_index, event in enumerate(events):
        character = event["character"]
        evidence = event["evidence"]
        matches = find_safe_quote_matches(window.text, evidence)
        if len(matches) != 1:
            issues.append(
                {
                    "chunk_id": window.chunk_id,
                    "event": event_index + 1,
                    "reason": "evidence_not_unique" if matches else "evidence_not_found",
                    "character": character,
                    "evidence": evidence,
                }
            )
            continue
        match = matches[0]
        if "\n" in match.raw_quote or "\r" in match.raw_quote:
            issues.append(
                {
                    "chunk_id": window.chunk_id,
                    "event": event_index + 1,
                    "reason": "evidence_crosses_scene_boundary",
                    "character": character,
                    "evidence": match.raw_quote,
                }
            )
            continue
        dimension = event["dimension"]
        if dimension == "form" and not _has_form_body_evidence(
            match.raw_quote,
            character,
            event["before"],
            event["after"],
        ):
            issues.append(
                {
                    "chunk_id": window.chunk_id,
                    "event": event_index + 1,
                    "reason": "form_without_body_change_evidence",
                    "character": character,
                    "evidence": match.raw_quote,
                }
            )
            continue
        document_span = SourceSpan(
            window.document_span.start + match.span.start,
            window.document_span.start + match.span.end,
        )
        before = event["before"]
        after = event["after"]
        if dimension == "form":
            before, after = _normalize_form_exit(
                evidence=match.raw_quote,
                before=before,
                after=after,
            )
        grounded_states = _ground_states(match.raw_quote, before, after)
        if grounded_states is None:
            issues.append(
                {
                    "chunk_id": window.chunk_id,
                    "event": event_index + 1,
                    "reason": "state_not_supported_by_evidence",
                    "character": character,
                    "evidence": match.raw_quote,
                }
            )
            continue
        before, after = grounded_states
        change = "change" if before and after else ("enter" if after else "exit")
        grounded.append(
            {
                "character_id": name_to_id[character],
                "evidence": match.raw_quote,
                "document_span": document_span.to_dict(),
                "dimension": dimension,
                "attribute": event["attribute"],
                "before": before,
                "after": after,
                "change": change,
            }
        )
    return tuple(grounded), tuple(issues)


def deduplicate_grounded_transitions(
    transitions: Sequence[Mapping[str, object]],
) -> tuple[dict[str, object], ...]:
    grouped: dict[tuple[object, ...], list[dict[str, object]]] = {}
    for transition in transitions:
        span = _mapping(transition.get("document_span"), "transition.document_span")
        signature = (
            transition.get("character_id"),
            transition.get("dimension"),
            transition.get("attribute"),
            transition.get("before"),
            transition.get("after"),
        )
        candidate = dict(transition)
        candidates = grouped.setdefault(signature, [])
        candidate_span = SourceSpan(
            _integer(span.get("start"), "transition.document_span.start"),
            _integer(span.get("end"), "transition.document_span.end"),
        )
        overlapping_index = next(
            (
                index
                for index, existing in enumerate(candidates)
                if _intersects(
                    candidate_span,
                    _span(existing["document_span"], "transition.document_span"),
                )
            ),
            None,
        )
        if overlapping_index is None:
            candidates.append(candidate)
            continue
        existing = candidates[overlapping_index]
        existing_span = _span(existing["document_span"], "transition.document_span")
        if (candidate_span.end - candidate_span.start, candidate_span.start) < (
            existing_span.end - existing_span.start,
            existing_span.start,
        ):
            candidates[overlapping_index] = candidate
    unique = [item for candidates in grouped.values() for item in candidates]
    return tuple(
        sorted(
            unique,
            key=lambda item: (
                _mapping(item["document_span"], "transition.document_span")["start"],
                str(item["character_id"]),
                str(item["dimension"]),
                str(item["attribute"]),
            ),
        )
    )


def _transition_effective_position(transition: Mapping[str, object]) -> int:
    span = _span(transition.get("document_span"), "transition.document_span")
    after = _string(transition.get("after"), "transition.after", allow_empty=True)
    if not after:
        return span.end
    evidence = _string(transition.get("evidence"), "transition.evidence")
    matches = find_safe_quote_matches(evidence, after)
    if not matches:
        raise ContractValidationError("transition after state is not grounded in evidence")
    return span.start + max(match.span.start for match in matches)


def _scene_expiry(
    *,
    document_text: str,
    transition: Mapping[str, object],
    chapter_spans: Sequence[SourceSpan],
) -> int:
    span = _span(transition.get("document_span"), "transition.document_span")
    newline = document_text.find("\n", span.end)
    line_end = len(document_text) if newline < 0 else newline
    chapter_end = next(
        (chapter.end for chapter in chapter_spans if chapter.start <= span.start < chapter.end),
        len(document_text),
    )
    return min(line_end, chapter_end)


def materialize_appearance_states(
    *,
    document_text: str,
    source_document_version_id: str,
    scopes: Mapping[str, object],
    fact_groups: Mapping[str, object],
    transitions: Sequence[Mapping[str, object]],
    review: Sequence[Mapping[str, object]],
    planned_chunks: int,
    model_calls: int,
) -> dict[str, object]:
    if fact_groups.get("document_hash") != sha256_text(document_text):
        raise ContractValidationError("fact groups document_hash does not match source text")
    if fact_groups.get("source_document_version_id") != source_document_version_id:
        raise ContractValidationError("fact groups refer to a different source document")
    groups: dict[str, Mapping[str, object]] = {}
    for group in _sequence(fact_groups.get("fact_groups"), "fact_groups.fact_groups"):
        item = _mapping(group, "canonical_fact")
        canonical_id = _string(item.get("canonical_fact_id"), "canonical_fact.canonical_fact_id")
        if canonical_id in groups:
            raise ContractValidationError("duplicate canonical fact id")
        groups[canonical_id] = item

    transition_items: list[Mapping[str, object]] = []
    for transition in transitions:
        item = _mapping(transition, "transition")
        span = _span(item.get("document_span"), "transition.document_span")
        evidence = _string(item.get("evidence"), "transition.evidence")
        if span.quote(document_text) != evidence:
            raise ContractValidationError("transition evidence does not replay from source text")
        transition_items.append(item)

    chapter_spans = tuple(
        _span(_mapping(chapter, "scope chapter").get("document_span"), "chapter.document_span")
        for chapter in _sequence(scopes.get("chapters"), "scopes.chapters")
    )
    if not chapter_spans:
        raise ContractValidationError("appearance scopes must contain chapter spans")

    by_character: dict[str, list[Mapping[str, object]]] = {}
    for transition in transition_items:
        by_character.setdefault(str(transition["character_id"]), []).append(transition)
    for items in by_character.values():
        items.sort(
            key=lambda item: (
                _transition_effective_position(item),
                {"life": 0, "form": 1, "scene": 2, "appearance": 3}.get(
                    str(item["dimension"]), 4
                ),
            )
        )

    assignments: list[dict[str, object]] = []
    assigned_ids: set[str] = set()
    for raw_assignment in _sequence(scopes.get("fact_assignments"), "scopes.fact_assignments"):
        assignment = dict(_mapping(raw_assignment, "scope assignment"))
        canonical_id = _string(assignment.get("canonical_fact_id"), "assignment.canonical_fact_id")
        group = groups.get(canonical_id)
        if group is None:
            raise ContractValidationError("scope assignment references unknown canonical fact")
        if canonical_id in assigned_ids:
            raise ContractValidationError("duplicate scope assignment canonical fact id")
        assigned_ids.add(canonical_id)
        if group.get("character_id") != assignment.get("character_id"):
            raise ContractValidationError("scope assignment character does not match canonical fact")
        fact_span = _span(group.get("document_fact_span"), "canonical_fact.document_fact_span")
        state = {"life": "unknown", "form": "unknown", "scene": "unknown"}
        scene_expires_at: int | None = None
        for transition in by_character.get(str(assignment["character_id"]), []):
            if _transition_effective_position(transition) > fact_span.start:
                break
            dimension = str(transition["dimension"])
            after = str(transition["after"]) or "unknown"
            if dimension == "life":
                state["life"] = after
                state["form"] = "unknown"
                state["scene"] = "unknown"
                scene_expires_at = None
            elif dimension == "form":
                state["form"] = after
            elif dimension == "scene":
                state["scene"] = after
                scene_expires_at = (
                    _scene_expiry(
                        document_text=document_text,
                        transition=transition,
                        chapter_spans=chapter_spans,
                    )
                    if after != "unknown"
                    else None
                )
        if scene_expires_at is not None and fact_span.start >= scene_expires_at:
            state["scene"] = "unknown"
        assignment.update(state)
        assignments.append(assignment)

    if assigned_ids != set(groups):
        raise ContractValidationError("scope assignments and canonical fact groups differ")

    counts = {dimension: sum(item[dimension] != "unknown" for item in assignments) for dimension in ("life", "form", "scene")}
    result = {
        "schema_version": DOCUMENT_APPEARANCE_STATES_VERSION,
        "transition_policy_version": APPEARANCE_TRANSITION_POLICY_VERSION,
        "source_document_version_id": source_document_version_id,
        "coverage_status": "complete",
        "processed_source_end": len(document_text),
        "transitions": [dict(item) for item in transitions],
        "fact_assignments": assignments,
        "review": [dict(item) for item in review],
        "summary": {
            "planned_chunks": planned_chunks,
            "model_calls": model_calls,
            "grounded_transitions": len(transitions),
            "review_items": len(review),
            "facts_with_life": counts["life"],
            "facts_with_form": counts["form"],
            "facts_with_scene": counts["scene"],
            "complete": True,
        },
    }
    return result


def build_transition_request(window: AppearanceTransitionChunk) -> AppearanceTransitionProviderRequest:
    names = [character.name for character in window.characters]
    return AppearanceTransitionProviderRequest(
        system_instruction=APPEARANCE_TRANSITION_SYSTEM_INSTRUCTION,
        user_payload=copy.deepcopy(window.model_payload()),
        response_schema=transition_response_schema(names),
    )
