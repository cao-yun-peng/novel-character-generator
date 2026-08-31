from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from typing import Mapping, Sequence

from .errors import ContractValidationError
from .m2 import (
    DescribeEvidenceRef,
    M2_PROMOTION_GROUNDING_POLICY_VERSION,
    M2PromotionEnvelope,
    M2PromotionModelInput,
    M2PromotionModelOutput,
    RemainingEvidenceFragment,
    ground_m2_promotion_output,
)
from .text import SourceSpan

PROMOTION_GROUNDING_REPLAY_VERSION = "promotion-grounding-replay-v1"
PROMOTION_GROUNDING_REPLAY_SUMMARY_VERSION = "promotion-grounding-replay-summary-v1"


def _read_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractValidationError(f"cannot read valid JSON from {path}") from exc


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _file_hash(path: Path) -> str:
    try:
        return sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise ContractValidationError(f"cannot hash source artifact {path}") from exc


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ContractValidationError(f"{label} must be an object")
    return value


def _sequence(value: object, label: str) -> Sequence[object]:
    if not isinstance(value, list):
        raise ContractValidationError(f"{label} must be an array")
    return value


def _string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ContractValidationError(f"{label} must be a non-empty string")
    return value


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ContractValidationError(f"{label} must be an integer")
    return value


def _span(value: object, label: str) -> SourceSpan:
    item = _mapping(value, label)
    if set(item) != {"start", "end"}:
        raise ContractValidationError(f"{label} must contain only start and end")
    return SourceSpan(
        _integer(item["start"], f"{label}.start"),
        _integer(item["end"], f"{label}.end"),
    )


def _parse_envelope(value: object, index: int) -> M2PromotionEnvelope:
    item = _mapping(value, f"promotion_envelopes[{index}]")
    describe_ref = _mapping(item.get("describe_source_ref"), "describe_source_ref")
    fragments = tuple(
        RemainingEvidenceFragment(
            fragment_ref=_string(fragment.get("fragment_ref"), "fragment_ref"),
            source_evidence_quote=_string(
                fragment.get("source_evidence_quote"),
                "source_evidence_quote",
            ),
            source_evidence_span=_span(
                fragment.get("source_evidence_span"),
                "source_evidence_span",
            ),
            fragment_quote=_string(fragment.get("fragment_quote"), "fragment_quote"),
            fragment_span=_span(fragment.get("fragment_span"), "fragment_span"),
        )
        for raw_fragment in _sequence(
            item.get("remaining_fragment_bindings"),
            "remaining_fragment_bindings",
        )
        for fragment in [_mapping(raw_fragment, "remaining fragment")]
    )
    model_input = _mapping(item.get("model_input"), "model_input")
    describe = _mapping(model_input.get("describe"), "model_input.describe")
    remaining_quotes = tuple(
        _string(quote, "remaining_evidence_quote")
        for quote in _sequence(
            describe.get("remaining_evidence_quotes"),
            "remaining_evidence_quotes",
        )
    )
    return M2PromotionEnvelope(
        source_document_version_id=_string(
            item.get("source_document_version_id"),
            "source_document_version_id",
        ),
        chunk_id=_string(item.get("chunk_id"), "chunk_id"),
        describe_source_ref=DescribeEvidenceRef(
            local_mention_id=_string(describe_ref.get("local_mention_id"), "local_mention_id"),
            packet_hash=_string(describe_ref.get("packet_hash"), "packet_hash"),
        ),
        remaining_fragment_bindings=fragments,
        context_version=_string(item.get("context_version"), "context_version"),
        resolver_version=_string(item.get("resolver_version"), "resolver_version"),
        pool_hash=_string(item.get("pool_hash"), "pool_hash"),
        promotion_hash=_string(item.get("promotion_hash"), "promotion_hash"),
        model_input=M2PromotionModelInput(
            mention_quote=_string(describe.get("mention_quote"), "mention_quote"),
            remaining_evidence_quotes=remaining_quotes,
            chunk_text=_string(model_input.get("chunk_text"), "chunk_text"),
        ),
        schema_version=_string(item.get("schema_version"), "schema_version"),
    )


def replay_promotion_grounding(
    *,
    source_run_dir: Path,
    output_dir: Path,
) -> dict[str, object]:
    """Re-ground saved promotion model outputs without calling a Provider."""
    if source_run_dir.resolve() == output_dir.resolve():
        raise ContractValidationError("promotion replay output_dir must differ from source_run_dir")
    envelope_path = source_run_dir / "promotion-envelopes.json"
    model_path = source_run_dir / "promotion-model-outputs.json"
    target_path = source_run_dir / "n3-target-appearance-packets.json"
    pool_path = source_run_dir / "n3-describe-pool-results.json"
    chunk_path = source_run_dir / "n3-chunk-results.json"
    envelopes_raw = _sequence(_read_json(envelope_path), "promotion envelopes")
    models_raw = _sequence(_read_json(model_path), "promotion model outputs")
    envelopes = tuple(_parse_envelope(value, index) for index, value in enumerate(envelopes_raw))

    models: dict[str, Mapping[str, object]] = {}
    for index, raw_model in enumerate(models_raw):
        model = _mapping(raw_model, f"promotion_model_outputs[{index}]")
        promotion_hash = _string(model.get("promotion_hash"), "promotion_hash")
        if promotion_hash in models:
            raise ContractValidationError("duplicate promotion model output hash")
        models[promotion_hash] = model
    if set(models) != {envelope.promotion_hash for envelope in envelopes}:
        raise ContractValidationError("promotion envelopes and saved model outputs do not match")

    records: list[dict[str, object]] = []
    issue_counts: dict[str, int] = {}
    for envelope in envelopes:
        saved = models[envelope.promotion_hash]
        if (
            saved.get("chunk_id") != envelope.chunk_id
            or saved.get("describe_local_mention_id")
            != envelope.describe_source_ref.local_mention_id
        ):
            raise ContractValidationError("saved promotion model output wrapper does not match envelope")
        parsed = M2PromotionModelOutput.parse(
            _mapping(saved.get("model_output"), "saved promotion model_output")
        )
        grounded = ground_m2_promotion_output(envelope, parsed)
        issues = [issue.to_dict() for issue in grounded.issues]
        for issue in issues:
            code = _string(issue.get("code"), "grounding issue code")
            issue_counts[code] = issue_counts.get(code, 0) + 1
        records.append(
            {
                "chunk_index": _integer(saved.get("chunk_index"), "chunk_index"),
                "chunk_id": envelope.chunk_id,
                "describe_local_mention_id": envelope.describe_source_ref.local_mention_id,
                "mention_quote": envelope.model_input.mention_quote,
                "grounded_result": grounded.to_packet_dict(),
                "grounding_issues": issues,
            }
        )

    records.sort(key=lambda item: (int(item["chunk_index"]), str(item["describe_local_mention_id"])))
    promoted = [
        character
        for record in records
        for character in _sequence(
            _mapping(record["grounded_result"], "grounded_result").get("promoted_characters"),
            "promoted_characters",
        )
    ]
    facts = [
        fact
        for raw_character in promoted
        for fact in _sequence(
            _mapping(raw_character, "promoted character").get("grounded_belongs_to_character"),
            "grounded_belongs_to_character",
        )
    ]
    replay_manifest = {
        "schema_version": PROMOTION_GROUNDING_REPLAY_VERSION,
        "source_run_dir": str(source_run_dir.resolve()),
        "grounding_policy_version": M2_PROMOTION_GROUNDING_POLICY_VERSION,
        "source_artifacts": {
            "promotion_envelopes": {"path": str(envelope_path.resolve()), "hash": _file_hash(envelope_path)},
            "promotion_model_outputs": {"path": str(model_path.resolve()), "hash": _file_hash(model_path)},
            "n3_target_packets": {"path": str(target_path.resolve()), "hash": _file_hash(target_path)},
        },
    }
    summary = {
        "schema_version": PROMOTION_GROUNDING_REPLAY_SUMMARY_VERSION,
        "grounding_policy_version": M2_PROMOTION_GROUNDING_POLICY_VERSION,
        "source_promotion_tasks": len(envelopes),
        "replayed_model_outputs": len(models),
        "provider_calls": 0,
        "promoted_characters": len(promoted),
        "promoted_grounded_facts": len(facts),
        "promotion_grounding_issues": sum(issue_counts.values()),
        "promotion_grounding_issues_by_code": issue_counts,
        "promotion_review_required_tasks": sum(bool(record["grounding_issues"]) for record in records),
        "review_required": bool(issue_counts),
        "complete": True,
    }
    _write_json(output_dir / "source-replay-manifest.json", replay_manifest)
    _write_json(output_dir / "promotion-envelopes.json", list(envelopes_raw))
    _write_json(output_dir / "promotion-model-outputs.json", list(models_raw))
    _write_json(output_dir / "promotion-grounded-results.json", records)
    _write_json(output_dir / "n3-target-appearance-packets.json", _read_json(target_path))
    if pool_path.exists():
        _write_json(output_dir / "n3-describe-pool-results.json", _read_json(pool_path))
    if chunk_path.exists():
        _write_json(output_dir / "n3-chunk-results.json", _read_json(chunk_path))
    _write_json(output_dir / "provider-traces.json", [])
    _write_json(output_dir / "failures.json", [])
    _write_json(output_dir / "summary.json", summary)
    return summary
