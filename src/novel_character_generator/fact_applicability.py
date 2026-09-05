"""Pure, evidence-scoped applicability shared by snapshots and render cards."""
from __future__ import annotations

import json
from hashlib import sha256
from typing import Mapping, Sequence

from .appearance_state_segments import transition_effective_position
from .errors import ContractValidationError

FACT_APPLICABILITY_POLICY_VERSION = "evidence-interval-applicability-v2"
APPLICABILITY_EVENTS_VERSION = "fact-applicability-events-v1"
EVENT_KINDS = ("continuity", "uncertain_gap", "remove", "replace")


def _hash(value: object) -> str:
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                            separators=(",", ":")).encode("utf-8")).hexdigest()


def validate_applicability_events(
    artifact: Mapping[str, object] | None, *, document_text: str,
    source_document_version_id: str, facts: Mapping[str, Mapping[str, object]],
) -> list[dict[str, object]]:
    """Bind already adjudicated semantics to exact source spans and explicit facts.

    This code-side contract is not a model payload. It verifies provenance and
    ownership, not the semantic truth of a reviewer's or model's event label.
    """
    if artifact is None:
        return []
    if not isinstance(artifact, Mapping) or set(artifact) != {
        "schema_version", "source_document_version_id", "document_hash", "events"
    }:
        raise ContractValidationError("invalid applicability events artifact fields")
    if (artifact["schema_version"] != APPLICABILITY_EVENTS_VERSION
            or artifact["source_document_version_id"] != source_document_version_id
            or artifact["document_hash"] != sha256(document_text.encode("utf-8")).hexdigest()):
        raise ContractValidationError("applicability events source/version mismatch")
    if not isinstance(artifact["events"], list):
        raise ContractValidationError("applicability events must be an array")
    result = {}
    for event in artifact["events"]:
        if not isinstance(event, Mapping) or set(event) != {
            "character_id", "kind", "fact_ids", "evidence", "document_span"
        }:
            raise ContractValidationError("invalid applicability event fields")
        span = event["document_span"]
        if (not isinstance(span, Mapping) or set(span) != {"start", "end"}
                or any(isinstance(span[k], bool) or not isinstance(span[k], int) for k in span)
                or not 0 <= span["start"] < span["end"] <= len(document_text)):
            raise ContractValidationError("applicability event span is outside source")
        if document_text[span["start"]:span["end"]] != event["evidence"]:
            raise ContractValidationError("applicability event evidence does not replay")
        if event["kind"] not in EVENT_KINDS:
            raise ContractValidationError("unsupported applicability event kind")
        ids = event["fact_ids"]
        if (not isinstance(ids, list) or not ids or any(not isinstance(i, str) for i in ids)
                or len(set(ids)) != len(ids)):
            raise ContractValidationError("event requires unique explicit fact_ids")
        for fact_id in ids:
            fact = facts.get(fact_id)
            if fact is None or fact["character_id"] != event["character_id"]:
                raise ContractValidationError("event references unknown or different character fact")
            if fact["document_fact_span"]["end"] > span["start"]:
                raise ContractValidationError("event must follow its target observation")
        normalized = {**dict(event), "fact_ids": sorted(ids), "document_span": dict(span)}
        event_id = "app-event-" + _hash({"source": source_document_version_id, **normalized})[:20]
        result[event_id] = {"event_id": event_id, **normalized}
    # Same-position close always wins over continuity, independent of input/chunk order.
    return sorted(result.values(), key=lambda e: (e["document_span"]["start"], e["event_id"]))


def select_state_segments(segments: Sequence[Mapping[str, object]],
                          selector: Mapping[str, object]) -> list[Mapping[str, object]]:
    fields = {"life_stage": "life", "form_state": "form", "scene_state": "scene"}
    position = selector["document_position"]
    return [segment for segment in segments
            if all(selector[k] is None or segment[v] == selector[k] for k, v in fields.items())
            and (position is None or segment["document_span"]["start"] <= position
                 < segment["document_span"]["end"])]


def evaluate_fact_applicability(
    *, fact: Mapping[str, object], assignment: Mapping[str, object],
    observed_segment: Mapping[str, object], target_segment: Mapping[str, object],
    segments: Sequence[Mapping[str, object]], transitions: Sequence[Mapping[str, object]],
    document_position: int, selected_chapter: int,
    events: Sequence[Mapping[str, object]] = (),
    candidate_facts: Sequence[Mapping[str, object]] = (),
    scene_events: Sequence[Mapping[str, object]] = (),
) -> dict[str, object]:
    """Explain inclusion/exclusion at a half-open source position.

    valid_interval is the interval supported by the selected evidence/rule, not
    a claim that an unknown physical state lasts until the document ends.
    """
    span = fact["document_fact_span"]
    start, observation_end = span["start"], span["end"]
    position = document_position
    fact_id = fact["canonical_fact_id"]
    persistence = assignment["persistence"]
    relevant = [e for e in events if fact_id in e["fact_ids"]]
    closures = [(e["document_span"]["end"], "removed" if e["kind"] == "remove" else "replaced",
                 e["event_id"]) for e in relevant if e["kind"] in {"remove", "replace"}]
    clothing = fact["category"] in {"clothing", "accessory"}
    for transition in transitions:
        effective = transition_effective_position(transition)
        if effective <= start:
            continue
        if transition["dimension"] == "life":
            closures.append((effective, "different_life", transition["transition_id"]))
        elif (transition["dimension"] == "appearance"
              and transition["attribute"] == fact["attribute"]
              and transition["before"] == fact["value"]
              and transition["document_span"]["start"] >= observation_end
              and sum(f["character_id"] == fact["character_id"]
                      and f["attribute"] == fact["attribute"]
                      and f["value"] == fact["value"]
                      and f["document_fact_span"]["end"] <= transition["document_span"]["start"]
                      for f in candidate_facts) == 1):
            closures.append((effective, "removed" if transition["change"] == "exit" else "replaced",
                             transition["transition_id"]))
    if not clothing and persistence == "scene":
        closures.extend((e["document_span"]["end"], "scene_boundary", e["event_id"])
                        for e in scene_events if e["character_id"] == fact["character_id"]
                        and e["document_span"]["end"] > start)
    closures.sort()
    end = closures[0][0] if closures else None

    unspecified = object()

    def answer(status: str, reason: str, *, lower=start, upper=unspecified, basis=()):
        return {"canonical_fact_id": fact_id, "status": status, "reason": reason,
                "observation_span": dict(span),
                "valid_interval": {"start": lower, "end": end if upper is unspecified else upper},
                "basis_event_ids": sorted(set(basis)), "persistence": persistence}

    if position < start:
        return answer("excluded", "future_observation")
    if end is not None and position >= end:
        closing = [c for c in closures if c[0] == end]
        return answer("excluded", closing[0][1], basis=[c[2] for c in closing])
    observed_index, target_index = observed_segment["sequence_index"], target_segment["sequence_index"]
    path = segments[observed_index:target_index + 1]
    if not path or any(s["life"] != observed_segment["life"] for s in path):
        return answer("excluded", "different_life")
    same_form = all(s["form"] == observed_segment["form"] for s in path)
    # Clothing can return after a temporary form, but never transfer to another form.
    if not same_form and not (clothing and target_segment["form"] == observed_segment["form"]):
        return answer("excluded", "different_form")
    # An applicability interval must not bridge an incompatible form segment.
    later_forms = [s["document_span"]["start"] for s in segments[target_index + 1:]
                   if s["form"] != target_segment["form"]]
    if later_forms:
        end = min(end, min(later_forms)) if end is not None else min(later_forms)
    if position < observation_end:
        return answer("active", "observed_at_document_position", upper=min(observation_end, end or observation_end))
    if persistence == "momentary":
        return answer("excluded", "expired_momentary", upper=min(observation_end, end or observation_end))
    gaps = [e for e in relevant if e["kind"] == "uncertain_gap" and e["document_span"]["end"] <= position]
    gap_end = max((e["document_span"]["end"] for e in gaps), default=0)
    continuity = [e for e in relevant if e["kind"] == "continuity"
                  and gap_end <= e["document_span"]["start"] <= position < e["document_span"]["end"]]
    if continuity:
        # Do not bridge unsupported gaps between separate evidence intervals.
        upper = min(max(e["document_span"]["end"] for e in continuity), end or float("inf"))
        return answer("active", "evidence_supported_continuity",
                      lower=min(e["document_span"]["start"] for e in continuity), upper=upper,
                      basis=[e["event_id"] for e in continuity])
    if gaps:
        return answer("provisional", "uncertain_continuity", lower=gap_end,
                      basis=[e["event_id"] for e in gaps])
    if clothing:
        return answer("provisional", "uncertain_continuity" if same_form else "restored_base_clothing_uncertain",
                      lower=start if same_form else target_segment["document_span"]["start"], upper=end)
    if persistence == "stable":
        return answer("active", "stable_same_life_form_path")
    if persistence == "persistent_until_changed":
        return answer("active", "persistent_until_attribute_or_state_change")
    if persistence == "scene":
        if assignment["chapter_number"] != selected_chapter or assignment["scene"] != target_segment["scene"]:
            return answer("excluded", "scene_boundary")
        return answer("provisional", "scene_chapter_upper_bound")
    return answer("provisional", "unknown_persistence_same_life_form_path")
