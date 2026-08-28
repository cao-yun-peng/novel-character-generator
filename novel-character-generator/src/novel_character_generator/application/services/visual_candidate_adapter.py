from __future__ import annotations

import hashlib
import json

from novel_character_generator.application.ports.entity_resolution import (
    GroundedCandidatePacket,
    GroundedFactCandidate,
    GroundedMentionCandidate,
    GroundedTemporalSignal,
)
from novel_character_generator.application.ports.extraction import (
    GroundedVisualExtractionResult,
    MentionDraft,
    ObservationDraft,
    VisualCandidateExtractionResult,
)
from novel_character_generator.domain.policies.grounding import (
    EvidenceLocation,
    locate_evidence_span,
)
from novel_character_generator.domain.policies.visual_fields import (
    canonical_field_path,
    is_plausible_age_signal,
    is_plausible_transformation_signal,
    is_visual_field,
    normalize_life_phase,
    semantic_visual_field_path,
    visual_field_semantic_issue,
)

_SAFE_FIELD_ALIASES = frozenset({"age.age", "age.age_stage", "face.hands"})


def _record_evidence_adjustment(
    warnings: list[str],
    *,
    source: str,
    location: EvidenceLocation,
) -> None:
    if location.status not in {"normalized", "repaired"}:
        return
    warnings.append(
        f"{location.status}_evidence:{source}:{location.repair_kind or 'unspecified'}"
    )


def adapt_visual_candidates(
    text: str,
    candidates: VisualCandidateExtractionResult,
) -> GroundedVisualExtractionResult:
    """Gate v3 candidates and adapt accepted facts to the current repository DTO."""

    entities = {entity.local_id: entity for entity in candidates.entities}
    mentions: dict[tuple[int, int, str], MentionDraft] = {}
    observations: list[ObservationDraft] = []
    warnings = [f"provider_deferred:{item.reason_code}" for item in candidates.deferred_items]

    for index, candidate in enumerate(candidates.visual_candidates):
        entity = entities[candidate.entity_ref]
        canonical_path = canonical_field_path(
            candidate.field_path,
            character_name=entity.representative_name,
        )
        if (
            not is_visual_field(canonical_path)
            or canonical_path == "appearance"
            or (
                canonical_path != candidate.field_path
                and candidate.field_path not in _SAFE_FIELD_ALIASES
            )
        ):
            warnings.append(f"rejected_visual_candidate:{index}:unsupported_or_noncanonical_field")
            continue
        semantic_path = semantic_visual_field_path(
            canonical_path,
            candidate.value,
            candidate.evidence_quote,
        )
        semantic_issue = visual_field_semantic_issue(
            semantic_path,
            candidate.value,
            candidate.evidence_quote,
        )
        if semantic_issue is not None:
            warnings.append(f"rejected_visual_candidate:{index}:{semantic_issue}")
            continue
        if semantic_path != canonical_path:
            warnings.append(
                f"normalized_visual_candidate:{index}:{canonical_path}:{semantic_path}"
            )
        elif canonical_path != candidate.field_path:
            warnings.append(
                f"normalized_visual_candidate:{index}:{candidate.field_path}:{canonical_path}"
            )
        if candidate.epistemic_status not in {"asserted", "negated"}:
            warnings.append(f"rejected_visual_candidate:{index}:non_asserted_epistemic_status")
            continue
        evidence = locate_evidence_span(
            text,
            candidate.evidence_quote,
            anchor_quote=entity.mention_quote,
        )
        if evidence.start is None or evidence.end is None or evidence.source_quote is None:
            warnings.append(f"rejected_visual_candidate:{index}:evidence_{evidence.status}")
            continue
        _record_evidence_adjustment(
            warnings,
            source=f"visual_candidate:{index}",
            location=evidence,
        )
        owner = locate_evidence_span(
            text,
            entity.mention_quote,
            anchor_quote=evidence.source_quote,
        )
        if owner.start is None or owner.end is None or owner.source_quote is None:
            warnings.append(f"rejected_visual_candidate:{index}:owner_{owner.status}")
            continue
        _record_evidence_adjustment(
            warnings,
            source=f"visual_candidate_owner:{index}",
            location=owner,
        )

        life_phase_key: str | None = None
        life_phase_label: str | None = None
        for signal in candidate.temporal_signals:
            if signal.kind == "age" and not is_plausible_age_signal(
                signal.label, signal.evidence_quote
            ):
                warnings.append(f"ignored_temporal_signal:{index}:age:invalid_age_semantics")
                continue
            if signal.kind == "transformation" and not is_plausible_transformation_signal(
                signal.label, signal.evidence_quote
            ):
                warnings.append(
                    f"ignored_temporal_signal:{index}:transformation:invalid_transformation_semantics"
                )
                continue
            signal_location = locate_evidence_span(
                text,
                signal.evidence_quote,
                anchor_quote=evidence.source_quote,
            )
            if signal_location.start is None:
                warnings.append(
                    f"ignored_temporal_signal:{index}:{signal.kind}:{signal_location.status}"
                )
                continue
            _record_evidence_adjustment(
                warnings,
                source=f"visual_candidate_signal:{index}:{signal.kind}",
                location=signal_location,
            )
            if signal.kind == "life_phase":
                life_phase_key, life_phase_label = normalize_life_phase(None, signal.label)
                break

        mention_key = (owner.start, owner.end, entity.local_id)
        mentions[mention_key] = MentionDraft(
            text=owner.source_quote,
            canonical_name=entity.representative_name,
            start=owner.start,
            end=owner.end,
            kind=entity.mention_kind,
        )
        observations.append(
            ObservationDraft(
                character_name=entity.representative_name,
                field_path=semantic_path,
                value=candidate.value,
                evidence_quote=evidence.source_quote,
                start=evidence.start,
                end=evidence.end,
                epistemic_status=(
                    "negated" if candidate.epistemic_status == "negated" else "asserted"
                ),
                confidence=candidate.confidence,
                life_phase_key=life_phase_key,
                life_phase_label=life_phase_label,
            )
        )

    return GroundedVisualExtractionResult(
        mentions=sorted(mentions.values(), key=lambda item: (item.start, item.end)),
        observations=observations,
        warnings=warnings,
    )


def ground_visual_candidates(
    text: str,
    candidates: VisualCandidateExtractionResult,
    *,
    mention_id_prefix: str,
) -> GroundedCandidatePacket:
    """Ground visual candidates without assigning any novel-level identity.

    The returned mention ids are scoped to this extraction run and source chunk.
    `representative_name` remains untrusted model context; it is deliberately not
    converted into a Character or a global alias here.
    """

    entities = {entity.local_id: entity for entity in candidates.entities}
    mentions: dict[str, GroundedMentionCandidate] = {}
    mention_ids_by_entity: dict[str, str] = {}
    facts: list[GroundedFactCandidate] = []
    temporal_signals: list[GroundedTemporalSignal] = []
    warnings = [f"provider_deferred:{item.reason_code}" for item in candidates.deferred_items]

    for entity in candidates.entities:
        anchor = next(
            (
                fact.evidence_quote
                for fact in candidates.visual_candidates
                if fact.entity_ref == entity.local_id
            ),
            None,
        )
        owner = locate_evidence_span(text, entity.mention_quote, anchor_quote=anchor)
        if owner.start is None or owner.end is None or owner.source_quote is None:
            warnings.append(f"rejected_entity:{entity.local_id}:owner_{owner.status}")
            continue
        _record_evidence_adjustment(
            warnings,
            source=f"entity:{entity.local_id}",
            location=owner,
        )
        mention_id = f"{mention_id_prefix}:{entity.local_id}:{owner.start}:{owner.end}"
        mention_ids_by_entity[entity.local_id] = mention_id
        mentions[mention_id] = GroundedMentionCandidate(
            mention_id=mention_id,
            local_entity_id=entity.local_id,
            representative_name=entity.representative_name,
            mention_text=owner.source_quote,
            mention_kind=entity.mention_kind,
            start=owner.start,
            end=owner.end,
            confidence=entity.confidence,
        )

    for index, candidate in enumerate(candidates.visual_candidates):
        entity = entities[candidate.entity_ref]
        fact_mention_id = mention_ids_by_entity.get(entity.local_id)
        if fact_mention_id is None:
            warnings.append(f"rejected_visual_candidate:{index}:owner_unlocatable")
            continue
        canonical_path = canonical_field_path(
            candidate.field_path,
            character_name=entity.representative_name,
        )
        if (
            not is_visual_field(canonical_path)
            or canonical_path == "appearance"
            or (
                canonical_path != candidate.field_path
                and candidate.field_path not in _SAFE_FIELD_ALIASES
            )
        ):
            warnings.append(f"rejected_visual_candidate:{index}:unsupported_or_noncanonical_field")
            continue
        semantic_path = semantic_visual_field_path(
            canonical_path,
            candidate.value,
            candidate.evidence_quote,
        )
        semantic_issue = visual_field_semantic_issue(
            semantic_path,
            candidate.value,
            candidate.evidence_quote,
        )
        if semantic_issue is not None:
            warnings.append(f"rejected_visual_candidate:{index}:{semantic_issue}")
            continue
        if semantic_path != canonical_path:
            warnings.append(
                f"normalized_visual_candidate:{index}:{canonical_path}:{semantic_path}"
            )
        elif canonical_path != candidate.field_path:
            warnings.append(
                f"normalized_visual_candidate:{index}:{candidate.field_path}:{canonical_path}"
            )
        if candidate.epistemic_status not in {"asserted", "negated"}:
            warnings.append(f"rejected_visual_candidate:{index}:non_asserted_epistemic_status")
            continue
        evidence = locate_evidence_span(
            text,
            candidate.evidence_quote,
            anchor_quote=entity.mention_quote,
        )
        if evidence.start is None or evidence.end is None or evidence.source_quote is None:
            warnings.append(f"rejected_visual_candidate:{index}:evidence_{evidence.status}")
            continue
        _record_evidence_adjustment(
            warnings,
            source=f"visual_candidate:{index}",
            location=evidence,
        )
        candidate_key = (
            "fact:"
            + hashlib.sha256(
                json.dumps(
                    {
                        "mention_id": fact_mention_id,
                        "field_path": semantic_path,
                        "value": candidate.value,
                        "start": evidence.start,
                        "end": evidence.end,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                    default=str,
                ).encode("utf-8")
            ).hexdigest()
        )
        life_phase_key: str | None = None
        life_phase_label: str | None = None
        for signal_index, signal in enumerate(candidate.temporal_signals):
            if signal.kind == "age" and not is_plausible_age_signal(
                signal.label, signal.evidence_quote
            ):
                warnings.append(f"ignored_temporal_signal:{index}:age:invalid_age_semantics")
                continue
            if signal.kind == "transformation" and not is_plausible_transformation_signal(
                signal.label, signal.evidence_quote
            ):
                warnings.append(
                    f"ignored_temporal_signal:{index}:transformation:invalid_transformation_semantics"
                )
                continue
            signal_location = locate_evidence_span(
                text,
                signal.evidence_quote,
                anchor_quote=evidence.source_quote,
            )
            if signal_location.start is None:
                warnings.append(
                    f"ignored_temporal_signal:{index}:{signal.kind}:{signal_location.status}"
                )
                continue
            _record_evidence_adjustment(
                warnings,
                source=f"visual_candidate_signal:{index}:{signal_index}",
                location=signal_location,
            )
            assert signal_location.end is not None
            assert signal_location.source_quote is not None
            signal_id = (
                "signal:"
                + hashlib.sha256(
                    (
                        f"{mention_id_prefix}:{index}:{signal_index}:"
                        f"{signal.kind}:{signal.label}:{signal_location.start}:"
                        f"{signal_location.end}"
                    ).encode()
                ).hexdigest()
            )
            temporal_signals.append(
                GroundedTemporalSignal(
                    signal_id=signal_id,
                    mention_id=fact_mention_id,
                    fact_candidate_key=candidate_key,
                    kind=signal.kind,
                    label=signal.label,
                    evidence_quote=signal_location.source_quote,
                    start=signal_location.start,
                    end=signal_location.end,
                    confidence=candidate.confidence,
                )
            )
            if signal.kind == "life_phase":
                life_phase_key, life_phase_label = normalize_life_phase(None, signal.label)
        facts.append(
            GroundedFactCandidate(
                mention_id=fact_mention_id,
                field_path=semantic_path,
                value=candidate.value,
                evidence_quote=evidence.source_quote,
                evidence_status=evidence.status,
                evidence_repair_kind=evidence.repair_kind,
                start=evidence.start,
                end=evidence.end,
                epistemic_status=(
                    "negated" if candidate.epistemic_status == "negated" else "asserted"
                ),
                confidence=candidate.confidence,
                candidate_key=candidate_key,
                life_phase_key=life_phase_key,
                life_phase_label=life_phase_label,
            )
        )

    for signal_index, signal in enumerate(candidates.temporal_signals):
        if signal.kind == "age" and not is_plausible_age_signal(
            signal.label, signal.evidence_quote
        ):
            warnings.append(
                f"ignored_temporal_signal:top:{signal_index}:age:invalid_age_semantics"
            )
            continue
        if signal.kind == "transformation" and not is_plausible_transformation_signal(
            signal.label, signal.evidence_quote
        ):
            warnings.append(
                "ignored_temporal_signal:top:"
                f"{signal_index}:transformation:invalid_transformation_semantics"
            )
            continue
        top_signal_mention_id = (
            mention_ids_by_entity.get(signal.entity_ref) if signal.entity_ref is not None else None
        )
        if signal.entity_ref is not None and top_signal_mention_id is None:
            warnings.append(f"ignored_temporal_signal:top:{signal_index}:owner_unlocatable")
            continue
        anchor_quote = (
            entities[signal.entity_ref].mention_quote if signal.entity_ref is not None else None
        )
        location = locate_evidence_span(text, signal.evidence_quote, anchor_quote=anchor_quote)
        if location.start is None or location.end is None or location.source_quote is None:
            warnings.append(
                f"ignored_temporal_signal:top:{signal_index}:{signal.kind}:{location.status}"
            )
            continue
        _record_evidence_adjustment(
            warnings,
            source=f"temporal_signal:{signal_index}",
            location=location,
        )
        signal_id = (
            "signal:"
            + hashlib.sha256(
                (
                    f"{mention_id_prefix}:top:{signal_index}:{signal.kind}:"
                    f"{signal.label}:{location.start}:{location.end}"
                ).encode()
            ).hexdigest()
        )
        temporal_signals.append(
            GroundedTemporalSignal(
                signal_id=signal_id,
                mention_id=top_signal_mention_id,
                fact_candidate_key=None,
                kind=signal.kind,
                label=signal.label,
                evidence_quote=location.source_quote,
                start=location.start,
                end=location.end,
                confidence=signal.confidence,
            )
        )

    return GroundedCandidatePacket(
        mentions=sorted(mentions.values(), key=lambda item: (item.start, item.end)),
        facts=facts,
        temporal_signals=temporal_signals,
        warnings=warnings,
    )
