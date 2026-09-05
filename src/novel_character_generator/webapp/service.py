"""Application services shared by HTTP and future task layers (read-only).

All functions are pure with respect to run artifacts: they read verified
inputs from :class:`RunRepository` and project them into view models.
They never call a provider and never mutate run outputs.
"""

from __future__ import annotations

from typing import Any, Mapping

from ..character_snapshot import build_character_snapshot
from ..errors import ContractValidationError
from .repository import RunRepository, RunSpec, WebRunError

API_SCHEMA_VERSION = "web-api-v1"
OFFSET_UNIT = "unicode_codepoint"
MAX_WINDOW_CODE_POINTS = 10000
SNAPSHOT_ARTIFACTS = ("fact_groups", "appearance_states", "label_projection")


def _require_mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise WebRunError("artifact_invalid", f"{label} has unexpected shape", status_code=500)
    return value


def _require_sequence(value: object, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise WebRunError("artifact_invalid", f"{label} has unexpected shape", status_code=500)
    return value


def validate_text_window(start: int, end: int, total: int) -> None:
    """Shared half-open window contract for every raw-text endpoint."""
    if start < 0 or end <= start or end > total:
        raise WebRunError(
            "invalid_range",
            f"window [{start}, {end}) is invalid for a document of {total} code points",
            status_code=422,
        )
    if end - start > MAX_WINDOW_CODE_POINTS:
        raise WebRunError(
            "invalid_range",
            f"window length {end - start} exceeds the maximum of {MAX_WINDOW_CODE_POINTS} code points",
            status_code=422,
        )


class WebService:
    def __init__(self, repository: RunRepository) -> None:
        self._repository = repository

    def _run(self, run_id: str) -> RunSpec:
        return self._repository.get_run(run_id)

    def _verify_document_binding(self, spec: RunSpec, artifact_name: str, artifact: Mapping[str, object]) -> None:
        checks = (
            ("document_hash", spec.document_hash),
            ("source_document_version_id", spec.source_document_version_id),
        )
        verified = False
        for field, expected in checks:
            declared = artifact.get(field)
            if declared is None:
                continue
            if declared != expected:
                raise WebRunError(
                    "document_binding_mismatch",
                    f"artifact {artifact_name} of run {spec.run_id} binds {field} {declared}, expected {expected}",
                )
            verified = True
        if not verified:
            raise WebRunError(
                "document_binding_mismatch",
                f"artifact {artifact_name} of run {spec.run_id} binds neither document_hash nor source_document_version_id",
            )

    # ---------------------------------------------------------------- runs

    def list_runs(self) -> dict[str, Any]:
        runs = []
        for spec in self._repository.list_runs():
            runs.append({
                "run_id": spec.run_id,
                "display_name": spec.display_name,
                "source_document_version_id": spec.source_document_version_id,
                "document_hash": spec.document_hash,
            })
        return {"schema_version": API_SCHEMA_VERSION, "runs": runs}

    # ---------------------------------------------------------- characters

    def list_characters(self, run_id: str) -> dict[str, Any]:
        spec = self._run(run_id)
        registry = self._repository.load_artifact(spec, "registry")
        projection = self._repository.load_artifact(spec, "label_projection")
        states = self._repository.load_artifact(spec, "appearance_states")
        for name, artifact in (("registry", registry), ("label_projection", projection), ("appearance_states", states)):
            self._verify_document_binding(spec, name, artifact)

        registry_characters = {
            entry["character_id"]: entry
            for entry in _require_sequence(registry.get("characters"), "registry characters")
            if isinstance(entry, Mapping) and isinstance(entry.get("character_id"), str)
        }
        projection_characters = {
            entry["character_id"]: entry
            for entry in _require_sequence(projection.get("characters"), "label_projection characters")
            if isinstance(entry, Mapping) and isinstance(entry.get("character_id"), str)
        }
        unknown_in_projection = sorted(set(projection_characters) - set(registry_characters))
        if unknown_in_projection:
            raise WebRunError(
                "artifact_binding_mismatch",
                f"label_projection references unknown characters: {unknown_in_projection[:5]}",
            )

        segment_counts: dict[str, int] = {}
        transition_counts: dict[str, int] = {}
        for segment in _require_sequence(states.get("state_segments"), "state_segments"):
            if isinstance(segment, Mapping) and isinstance(segment.get("character_id"), str):
                segment_counts[segment["character_id"]] = segment_counts.get(segment["character_id"], 0) + 1
        for transition in _require_sequence(states.get("transitions"), "transitions"):
            if isinstance(transition, Mapping) and isinstance(transition.get("character_id"), str):
                transition_counts[transition["character_id"]] = transition_counts.get(transition["character_id"], 0) + 1

        actionable_by_character: dict[str, int] = {}
        for item in _require_sequence(projection.get("actionable_review_items"), "actionable_review_items"):
            if isinstance(item, Mapping) and isinstance(item.get("subject_character_id"), str):
                actionable_by_character[item["subject_character_id"]] = (
                    actionable_by_character.get(item["subject_character_id"], 0) + 1
                )

        characters = []
        for character_id, entry in registry_characters.items():
            projection_entry = projection_characters.get(character_id)
            labels = []
            if projection_entry is not None:
                for label in _require_sequence(projection_entry.get("labels"), "labels"):
                    if isinstance(label, Mapping):
                        labels.append({
                            key: label.get(key)
                            for key in ("label_id", "label_quote", "label_kind", "label_stability",
                                        "source_label_role", "selection_status")
                        })
            conflicts = entry.get("possible_conflicts")
            characters.append({
                "character_id": character_id,
                "identity_status": entry.get("identity_status"),
                "canonical_label": entry.get("canonical_label"),
                "canonical_label_status": entry.get("canonical_label_status"),
                "labels": labels,
                "state_segment_count": segment_counts.get(character_id, 0),
                "transition_count": transition_counts.get(character_id, 0),
                "open_conflict_count": len(conflicts) if isinstance(conflicts, list) else 0,
                "actionable_review_count": actionable_by_character.get(character_id, 0),
            })
        characters.sort(key=lambda item: (-item["actionable_review_count"], -item["state_segment_count"], item["character_id"]))
        return {
            "schema_version": API_SCHEMA_VERSION,
            "run_id": spec.run_id,
            "source_document_version_id": spec.source_document_version_id,
            "characters": characters,
        }

    # -------------------------------------------------------------- states

    def get_character_states(self, run_id: str, character_id: str) -> dict[str, Any]:
        spec = self._run(run_id)
        states = self._repository.load_artifact(spec, "appearance_states")
        self._verify_document_binding(spec, "appearance_states", states)

        segments = []
        known = False
        for segment in _require_sequence(states.get("state_segments"), "state_segments"):
            if not isinstance(segment, Mapping) or segment.get("character_id") != character_id:
                continue
            known = True
            segments.append({
                key: segment.get(key)
                for key in ("state_segment_id", "sequence_index", "document_span", "life", "form", "scene",
                            "start_boundary", "end_boundary", "observed_fact_ids")
            })
        if not known:
            raise WebRunError("character_not_found", f"unknown character_id: {character_id}", status_code=404)
        segments.sort(key=lambda item: item["sequence_index"] if isinstance(item.get("sequence_index"), int) else 0)

        transitions = [
            {key: transition.get(key)
             for key in ("transition_id", "evidence", "document_span", "dimension", "attribute",
                         "before", "after", "change")}
            for transition in _require_sequence(states.get("transitions"), "transitions")
            if isinstance(transition, Mapping) and transition.get("character_id") == character_id
        ]

        return {
            "schema_version": API_SCHEMA_VERSION,
            "run_id": spec.run_id,
            "character_id": character_id,
            "offset_unit": OFFSET_UNIT,
            "coverage_status": states.get("coverage_status"),
            "processed_source_end": states.get("processed_source_end"),
            "state_segments": segments,
            "transitions": transitions,
        }

    # ------------------------------------------------------------ snapshot

    def build_snapshot(
        self, run_id: str, character_id: str, *, document_position: int | None,
        life_stage: str | None = None, form_state: str | None = None, scene_state: str | None = None,
        explain: bool = False,
    ) -> dict[str, Any]:
        spec = self._run(run_id)
        text = self._repository.load_document_text(spec)
        inputs = {name: self._repository.load_artifact(spec, name) for name in SNAPSHOT_ARTIFACTS}
        for name, artifact in inputs.items():
            self._verify_document_binding(spec, name, artifact)
        known_characters = {
            segment.get("character_id")
            for segment in _require_sequence(inputs["appearance_states"].get("state_segments"), "state_segments")
            if isinstance(segment, Mapping)
        }
        if character_id not in known_characters:
            raise WebRunError("character_not_found", f"unknown character_id: {character_id}", status_code=404)
        try:
            snapshot = build_character_snapshot(
                document_text=text,
                fact_groups=inputs["fact_groups"],
                appearance_states=inputs["appearance_states"],
                label_projection=inputs["label_projection"],
                run_id=spec.snapshot_namespace,
                character_id=character_id,
                document_position=document_position,
                life_stage=life_stage,
                form_state=form_state,
                scene_state=scene_state,
                explain=explain,
            )
        except ContractValidationError as error:
            raise WebRunError("snapshot_invalid", str(error), status_code=422) from error
        return snapshot

    # ---------------------------------------------------------- text window

    def get_text_window(self, run_id: str, start: int, end: int) -> dict[str, Any]:
        spec = self._run(run_id)
        text = self._repository.load_document_text(spec)
        total = len(text)
        validate_text_window(start, end, total)
        return {
            "schema_version": API_SCHEMA_VERSION,
            "run_id": spec.run_id,
            "source_document_version_id": spec.source_document_version_id,
            "document_hash": spec.document_hash,
            "offset_unit": OFFSET_UNIT,
            "total_code_points": total,
            "start": start,
            "end": end,
            "text": text[start:end],
        }

    # ------------------------------------------------------------- reviews

    def list_reviews(self, run_id: str) -> dict[str, Any]:
        spec = self._run(run_id)
        registry = self._repository.load_artifact(spec, "registry")
        projection = self._repository.load_artifact(spec, "label_projection")
        states = self._repository.load_artifact(spec, "appearance_states")
        for name, artifact in (("registry", registry), ("label_projection", projection), ("appearance_states", states)):
            self._verify_document_binding(spec, name, artifact)

        actionable = []
        for item in _require_sequence(projection.get("actionable_review_items"), "actionable_review_items"):
            if isinstance(item, Mapping):
                actionable.append({"source": "identity", **{k: item.get(k) for k in item if k != "source"}})
        audit = []
        for item in _require_sequence(projection.get("audit_items"), "audit_items"):
            if isinstance(item, Mapping):
                audit.append({"source": "identity", **{k: item.get(k) for k in item if k != "source"}})
        state_review = [
            {"source": "appearance_states", **{k: item.get(k) for k in item if k != "source"}}
            for item in _require_sequence(states.get("review"), "appearance_states review")
            if isinstance(item, Mapping)
        ]
        open_conflicts = []
        for entry in _require_sequence(registry.get("characters"), "registry characters"):
            if not isinstance(entry, Mapping):
                continue
            conflicts = entry.get("possible_conflicts")
            if isinstance(conflicts, list) and conflicts:
                open_conflicts.append({
                    "source": "registry",
                    "character_id": entry.get("character_id"),
                    "conflicts": conflicts,
                })
        return {
            "schema_version": API_SCHEMA_VERSION,
            "run_id": spec.run_id,
            "actionable": actionable,
            "audit": audit,
            "state_review": state_review,
            "open_conflicts": open_conflicts,
        }
