"""Re-ground saved M2 outputs into a new run, without a network provider."""
from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from typing import Mapping

from .errors import ContractValidationError
from .m2 import M2_ATTRIBUTION_GROUNDING_POLICY_VERSION, M2AttributionModelOutput, build_m2_attribution_envelopes
from .m2_batch import (
    _expect_mapping, _expect_string, _load_model_outputs, _parse_source_manifest,
    _read_json, _replay_n2, _write_json, run_m2_from_m1_run,
)


def _canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _index_records(value: object, *, envelopes: bool) -> dict[tuple[str, str], Mapping[str, object]]:
    if not isinstance(value, list):
        raise ContractValidationError("saved M2 records must be arrays")
    result = {}
    for raw in value:
        record = _expect_mapping(raw, label="saved M2 record")
        if envelopes:
            ref = _expect_mapping(record.get("target_character_ref"), label="saved target reference")
            key = (ref.get("chunk_id"), ref.get("local_mention_id"))
        else:
            key = (record.get("chunk_id"), record.get("target_local_mention_id"))
        key = tuple(_expect_string(item, label="saved task identity") for item in key)
        if key in result:
            raise ContractValidationError("duplicate saved M2 task identity")
        result[key] = record
    return result


class _SavedOutputs:
    def __init__(self, outputs: Mapping[str, object], lineage: Mapping[str, object]):
        self.outputs = outputs
        self.cache_identity = {"provider": "offline-m2-replay-v1", "lineage": dict(lineage)}

    def generate(self, request):
        key = _canonical(request.user_payload)
        if key not in self.outputs:
            raise ContractValidationError("current M2 payload has no uniquely associated saved output")
        return self.outputs[key]


def replay_m2_grounding(
    *, document_text: str, source_m1_run_dir: Path, source_m2_run_dir: Path, output_dir: Path,
) -> dict[str, object]:
    """Explicit replay validates all inputs before writing; sources stay read-only."""
    destination = output_dir.resolve()
    for source in (source_m1_run_dir.resolve(), source_m2_run_dir.resolve()):
        if destination.is_relative_to(source) or source.is_relative_to(destination):
            raise ContractValidationError("replay output must be separate from source run directories")
    manifest = _parse_source_manifest(_read_json(source_m1_run_dir / "manifest.json"), document_text)
    n2, _ = _replay_n2(document_text=document_text, manifest=manifest,
                       model_outputs=_load_model_outputs(source_m1_run_dir))
    chunks = {entry.chunk_id: entry for entry in manifest.chunks}
    current = {}
    for packet in n2:
        for envelope in build_m2_attribution_envelopes(
            packet, chunk_text=chunks[packet.chunk_id].chunk_source_span.quote(document_text),
        ):
            current[(packet.chunk_id, envelope.target_character_ref.local_mention_id)] = envelope
    saved_envelopes = _index_records(_read_json(source_m2_run_dir / "m2-envelopes.json"), envelopes=True)
    saved_outputs = _index_records(_read_json(source_m2_run_dir / "m2-model-outputs.json"), envelopes=False)
    if set(current) != set(saved_envelopes) or set(current) != set(saved_outputs):
        raise ContractValidationError("saved M2 task set does not match current M1/N2 preparation")
    payload_outputs = {}
    for key, envelope in current.items():
        saved, output = saved_envelopes[key], saved_outputs[key]
        if (saved.get("target_character_ref") != envelope.target_character_ref.to_dict()
                or saved.get("model_input") != envelope.model_payload()):
            raise ContractValidationError("saved M2 source binding or model payload does not match current input")
        if (not saved.get("task_cache_key")
                or saved.get("task_cache_key") != output.get("task_cache_key")):
            raise ContractValidationError("saved M2 envelope/output association is inconsistent")
        parsed = M2AttributionModelOutput.parse(output.get("model_output")).to_dict()
        payload_key = _canonical(envelope.model_payload())
        if payload_key in payload_outputs and payload_outputs[payload_key] != parsed:
            raise ContractValidationError("identical payloads have divergent saved outputs; replay is ambiguous")
        payload_outputs[payload_key] = parsed
    source_files = [
        source_m1_run_dir / "manifest.json", source_m1_run_dir / "m1-model-outputs.json",
        source_m2_run_dir / "m2-envelopes.json", source_m2_run_dir / "m2-model-outputs.json",
    ]
    lineage = {
        "schema_version": "m2-grounding-replay-lineage-v1",
        "source_files": [{"path": str(p.resolve()), "sha256": sha256(p.read_bytes()).hexdigest()}
                         for p in source_files],
    }
    lineage_path = output_dir / "grounding-replay-lineage.json"
    if lineage_path.exists() and _read_json(lineage_path) != lineage:
        raise ContractValidationError("existing replay lineage does not match source files")
    summary = run_m2_from_m1_run(
        document_text=document_text, source_run_dir=source_m1_run_dir,
        provider=_SavedOutputs(payload_outputs, lineage), output_dir=output_dir,
    )
    _write_json(lineage_path, lineage)
    summary.update({
        "mode": "offline_grounding_replay", "replayed_model_outputs": len(current),
        "new_provider_calls": 0, "grounding_policy_version": M2_ATTRIBUTION_GROUNDING_POLICY_VERSION,
    })
    _write_json(output_dir / "summary.json", summary)
    return summary
