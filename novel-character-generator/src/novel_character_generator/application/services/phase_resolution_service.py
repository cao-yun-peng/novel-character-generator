from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from typing import cast

from novel_character_generator.application.ports.phase_resolution import (
    CharacterLifePhaseDraft,
    CharacterPhaseResolutionInput,
    CharacterPhaseResolutionResult,
    ObservationScopeDecision,
    PhaseSignalInput,
    PresentationMode,
    RealityStatus,
    ScopeType,
)
from novel_character_generator.domain.policies.visual_fields import (
    LIFE_PHASE_LABELS,
    normalize_age_stage,
    normalize_life_phase,
)

_PRESENTATION_LABELS = {
    "flashback": ("回忆", "回想", "往事", "昔日", "flashback"),
    "flashforward": ("预叙", "未来", "flashforward"),
    "dream": ("梦中", "梦境", "梦里", "dream"),
    "illusion": ("幻觉", "幻境", "illusion"),
    "rumor": ("传闻", "据说", "听说", "rumor"),
    "hypothetical": ("假如", "如果", "假设", "hypothetical"),
}

_AGE_STAGE_LABELS = {
    "childhood": "幼年",
    "adolescence": "少年期",
    "adulthood": "成年期",
    "elderly": "老年期",
}
_CHINESE_DIGITS = {
    "零": 0,
    "〇": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}
_REINCARNATION_MARKERS = (
    "前世",
    "前一世",
    "转生",
    "转世",
    "重生",
    "来世",
    "来到这个世界",
    "previous life",
    "past life",
    "reincarn",
    "reborn",
)


def _stable_key(prefix: str, label: str, evidence: str) -> str:
    token = re.sub(r"[^a-z0-9]+", "_", label.casefold()).strip("_")
    digest = hashlib.sha256(f"{label}\n{evidence}".encode()).hexdigest()[:12]
    return f"{prefix}_{token[:60]}_{digest}" if token else f"{prefix}_{digest}"


def _phase_identity(signal: PhaseSignalInput) -> tuple[str, str, str | None]:
    key, label = normalize_life_phase(None, signal.label)
    if key is None:
        key = _stable_key("phase", signal.label, signal.evidence_quote)
        label = signal.label.strip()
    age_stage = normalize_age_stage(key)
    if key not in LIFE_PHASE_LABELS and age_stage == key:
        age_stage = None
    return key, label or signal.label.strip(), age_stage


def _chinese_number(value: str) -> int | None:
    if not value:
        return None
    if all(character in _CHINESE_DIGITS for character in value):
        return int("".join(str(_CHINESE_DIGITS[character]) for character in value))
    total = 0
    current = 0
    unit_seen = False
    for character in value:
        if character in _CHINESE_DIGITS:
            current = _CHINESE_DIGITS[character]
        elif character == "十":
            total += (current or 1) * 10
            current = 0
            unit_seen = True
        elif character == "百":
            total += (current or 1) * 100
            current = 0
            unit_seen = True
        else:
            return None
    return total + current if unit_seen or current else None


def _age_value(text: str) -> int | None:
    arabic = [int(item) for item in re.findall(r"(\d{1,3})(?=\s*(?:岁|years? old))", text)]
    chinese_tokens = re.findall(
        r"([零〇一二两三四五六七八九十百]+(?:[、至到~-][零〇一二两三四五六七八九十百]+)*)"
        r"(?=岁)",
        text,
    )
    chinese: list[int] = []
    for token in chinese_tokens:
        for part in re.split(r"[、至到~-]", token):
            parsed = _chinese_number(part)
            if parsed is not None:
                chinese.append(parsed)
    decades = []
    for token in re.findall(r"([零〇一二两三四五六七八九十百]+)(?=旬)", text):
        parsed = _chinese_number(token)
        if parsed is not None:
            decades.append(parsed * 10)
    values = [*arabic, *chinese, *decades]
    return max(values) if values else None


def _age_stage(signal: PhaseSignalInput) -> str | None:
    text = f"{signal.label} {signal.evidence_quote}".casefold()
    markers = {
        "childhood": ("幼年", "儿童", "孩童", "孩子", "年纪还小", "child"),
        "adolescence": ("少年", "青少年", "adolesc"),
        "adulthood": ("成年", "青年", "adult"),
        "elderly": ("老年", "年迈", "高龄", "elderly"),
    }
    for stage, values in markers.items():
        if any(value in text for value in values):
            return stage
    age = _age_value(text)
    if age is None:
        return None
    if age < 13:
        return "childhood"
    if age < 18:
        return "adolescence"
    if age < 60:
        return "adulthood"
    return "elderly"


def _has_reincarnation_context(signals: list[PhaseSignalInput]) -> bool:
    text = " ".join(f"{item.label} {item.evidence_quote}" for item in signals).casefold()
    return any(marker in text for marker in _REINCARNATION_MARKERS)


def _is_reincarnation_signal(signal: PhaseSignalInput) -> bool:
    text = f"{signal.label} {signal.evidence_quote}".casefold()
    return any(marker in text for marker in _REINCARNATION_MARKERS)


def _presentation_mode(label: str) -> PresentationMode | None:
    token = label.casefold()
    for mode, markers in _PRESENTATION_LABELS.items():
        if any(marker in token for marker in markers):
            return cast(PresentationMode, mode)
    if token in {"direct", "当前", "现在", "直接叙述"}:
        return "direct"
    return None


def _reality_status(presentation_mode: PresentationMode) -> RealityStatus:
    if presentation_mode in {"dream", "illusion"}:
        return "subjective"
    if presentation_mode == "rumor":
        return "alleged"
    if presentation_mode == "hypothetical":
        return "counterfactual"
    return "canonical"


def _transformation_key(signal: PhaseSignalInput) -> str:
    return _stable_key("form", signal.label, signal.evidence_quote)


def resolve_character_phases(
    request: CharacterPhaseResolutionInput,
) -> CharacterPhaseResolutionResult:
    phase_groups: dict[str, list[tuple[PhaseSignalInput, str, str | None]]] = defaultdict(list)
    explicit_phase_signals = [item for item in request.signals if item.kind == "life_phase"]
    if explicit_phase_signals:
        for signal in explicit_phase_signals:
            key, label, age_stage = _phase_identity(signal)
            phase_groups[key].append((signal, label, age_stage))
    else:
        age_signals = [
            (signal, stage)
            for signal in request.signals
            if signal.kind == "age"
            for stage in [_age_stage(signal)]
            if stage is not None
        ]
        stage_chapters = {
            stage: min(
                signal.chapter_ordinal if signal.chapter_ordinal is not None else 2**31
                for signal, candidate_stage in age_signals
                if candidate_stage == stage
            )
            for stage in {stage for _, stage in age_signals}
        }
        reincarnation = (
            _has_reincarnation_context(request.signals)
            and "adulthood" in stage_chapters
            and "childhood" in stage_chapters
            and stage_chapters["adulthood"] < stage_chapters["childhood"]
        )
        for signal, stage in age_signals:
            key = f"age_{stage}"
            label = _AGE_STAGE_LABELS[stage]
            if reincarnation and stage == "adulthood":
                key, label = "past_life", LIFE_PHASE_LABELS["past_life"]
            elif reincarnation and stage == "childhood":
                key, label = (
                    "reincarnated_childhood",
                    LIFE_PHASE_LABELS["reincarnated_childhood"],
                )
            phase_groups[key].append((signal, label, stage))

    ordered_groups = sorted(
        phase_groups.items(),
        key=lambda item: (
            min(
                signal.chapter_ordinal if signal.chapter_ordinal is not None else 2**31
                for signal, _, _ in item[1]
            ),
            item[0],
        ),
    )
    phases: list[CharacterLifePhaseDraft] = []
    for index, (phase_key, items) in enumerate(ordered_groups):
        chapters = sorted(
            signal.chapter_ordinal for signal, _, _ in items if signal.chapter_ordinal is not None
        )
        next_start: int | None = None
        if index + 1 < len(ordered_groups):
            next_chapters = [
                signal.chapter_ordinal
                for signal, _, _ in ordered_groups[index + 1][1]
                if signal.chapter_ordinal is not None
            ]
            if next_chapters:
                next_start = min(next_chapters)
        phases.append(
            CharacterLifePhaseDraft(
                phase_key=phase_key,
                label=items[0][1],
                phase_order=index,
                age_stage=items[0][2],
                start_chapter_ordinal=chapters[0] if chapters else None,
                end_chapter_ordinal=(next_start - 1 if next_start is not None else None),
                evidence_signal_ids=[signal.id for signal, _, _ in items],
                confidence=min(signal.confidence for signal, _, _ in items),
                status="active",
            )
        )
    phases_by_key = {item.phase_key: item for item in phases}

    def phase_for_chapter(chapter: int | None) -> CharacterLifePhaseDraft | None:
        if chapter is None:
            return None
        candidates = [
            phase
            for phase in phases
            if (phase.start_chapter_ordinal is None or phase.start_chapter_ordinal <= chapter)
            and (phase.end_chapter_ordinal is None or chapter <= phase.end_chapter_ordinal)
        ]
        return candidates[0] if len(candidates) == 1 else None

    scope_decisions: list[ObservationScopeDecision] = []
    for observation in request.observations:
        related = [signal for signal in request.signals if observation.id in signal.observation_ids]
        phase_keys = {
            _phase_identity(signal)[0] for signal in related if signal.kind == "life_phase"
        }
        if not phase_keys and not explicit_phase_signals:
            phase_keys = {
                key
                for signal in related
                if signal.kind == "age"
                for stage in [_age_stage(signal)]
                if stage is not None
                for key, items in phase_groups.items()
                if any(candidate.id == signal.id for candidate, _, _ in items)
            }
        presentation_modes = {
            mode
            for signal in related
            if signal.kind == "presentation"
            for mode in [_presentation_mode(signal.label)]
            if mode is not None
        }
        unknown_presentation = any(
            signal.kind == "presentation" and _presentation_mode(signal.label) is None
            for signal in related
        )
        transformations = {
            _transformation_key(signal) for signal in related if signal.kind == "transformation"
        }
        reasons: list[str] = []
        if len(phase_keys) > 1:
            reasons.append("ambiguous_life_phase")
        if len(presentation_modes) > 1 or unknown_presentation:
            reasons.append("ambiguous_presentation")
        if len(transformations) > 1:
            reasons.append("ambiguous_transformation")
        if any(
            signal.kind == "other" and not _is_reincarnation_signal(signal)
            for signal in related
        ):
            reasons.append("unsupported_special_signal")

        has_direct_phase_evidence = len(phase_keys) == 1
        selected_phase_key = next(iter(phase_keys), None) if len(phase_keys) == 1 else None
        phase = phases_by_key.get(selected_phase_key) if selected_phase_key is not None else None
        if phase is None and not phase_keys:
            phase = phase_for_chapter(observation.chapter_ordinal)
            selected_phase_key = phase.phase_key if phase is not None else None
        if any(signal.kind == "time_jump" for signal in related) and not has_direct_phase_evidence:
            reasons.append("unresolved_time_jump")
        presentation_mode: PresentationMode = (
            next(iter(presentation_modes)) if len(presentation_modes) == 1 else "direct"
        )
        transformation = next(iter(transformations)) if len(transformations) == 1 else None
        start_chapter = observation.chapter_ordinal
        end_chapter = phase.end_chapter_ordinal if phase is not None else None
        scope_type: ScopeType = "persistent" if phase is not None else "unknown"
        if transformation is not None:
            scope_type = "chapter"
            start_chapter = observation.chapter_ordinal
            end_chapter = observation.chapter_ordinal
        confidence_values = [observation.confidence, *(item.confidence for item in related)]
        scope_decisions.append(
            ObservationScopeDecision(
                observation_id=observation.id,
                phase_key=selected_phase_key,
                presentation_mode=presentation_mode,
                reality_status=_reality_status(presentation_mode),
                transformation_state=transformation,
                scope_type=scope_type,
                start_chapter_ordinal=start_chapter,
                end_chapter_ordinal=end_chapter,
                status="needs_review" if reasons else "final",
                confidence=min(confidence_values),
                evidence_signal_ids=[item.id for item in related],
                reason_codes=reasons,
            )
        )
    return CharacterPhaseResolutionResult(
        phases=phases,
        scope_decisions=scope_decisions,
    )
