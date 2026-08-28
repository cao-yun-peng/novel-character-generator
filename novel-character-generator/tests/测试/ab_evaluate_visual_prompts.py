r"""Compare frozen and candidate R1 prompts through the same production provider path."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from novel_character_generator.application.ports.extraction import (  # noqa: E402
    VisualCandidateExtractionResult,
)
from novel_character_generator.application.services.extraction_evaluation_service import (  # noqa: E402
    ExtractionSeedCase,
    evaluate_extraction_case,
    load_extraction_seed_dataset,
)
from novel_character_generator.application.services.visual_candidate_adapter import (  # noqa: E402
    adapt_visual_candidates,
    ground_visual_candidates,
)
from novel_character_generator.domain.entities.document import TextChunk  # noqa: E402
from novel_character_generator.domain.policies.text_processing import (  # noqa: E402
    build_chunks,
    decode_text,
    detect_chapters,
    normalize_text,
)
from novel_character_generator.infrastructure.llm.openai_compatible import (  # noqa: E402
    EXTRACTION_SYSTEM_PROMPT_V2_5,
    EXTRACTION_SYSTEM_PROMPT_V2_6,
    OpenAICompatibleExtractionProvider,
)
from novel_character_generator.settings import get_settings  # noqa: E402

DEFAULT_SEED = PROJECT_ROOT / "tests" / "evaluation" / "visual_extraction_seed_v1.json"
DEFAULT_REAL = PROJECT_ROOT / "tests" / "evaluation" / "r1_prompt_ab_real_v1.json"
GENERIC_EXPLICIT_NAME_SURFACES = {
    "girl",
    "boy",
    "elder",
    "youth",
    "少女",
    "少年",
    "老者",
    "青年",
    "女孩",
    "男孩",
    "中年男子",
    "道童",
}


def _sample_ids(value: str) -> set[str]:
    ids = {item.strip() for item in value.split(",") if item.strip()}
    if not ids:
        raise argparse.ArgumentTypeError("at least one sample id is required")
    return ids


def _provider(system_prompt: str, prompt_version: str) -> OpenAICompatibleExtractionProvider:
    settings = get_settings()
    if settings.llm_provider == "mock":
        raise RuntimeError("real_provider_required_for_prompt_ab")
    if settings.llm_api_key is None or settings.llm_model is None:
        raise RuntimeError("llm_credentials_or_model_missing")
    return OpenAICompatibleExtractionProvider(
        provider=settings.llm_provider,
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key.get_secret_value(),
        model=settings.llm_model,
        timeout_seconds=settings.llm_timeout_seconds,
        wire_api=settings.llm_wire_api,
        thinking_enabled=settings.llm_thinking_enabled,
        reasoning_effort=settings.llm_reasoning_effort,
        max_output_tokens=settings.llm_max_output_tokens,
        total_deadline_seconds=settings.llm_total_deadline_seconds,
        max_items_per_result=settings.llm_max_items_per_result,
        max_retries=settings.llm_max_retries,
        system_prompt=system_prompt,
        prompt_version=prompt_version,
    )


def _chunks(path: Path, target_tokens: int) -> list[TextChunk]:
    decoded, _ = decode_text(path.read_bytes())
    normalized = normalize_text(decoded)
    chapters = detect_chapters(normalized.text)
    return list(build_chunks(normalized, chapters, target_tokens=target_tokens))


def _load_real_samples(
    path: Path,
) -> tuple[list[dict[str, Any]], dict[str, ExtractionSeedCase]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    target_tokens = int(payload["chunk_tokens"])
    chunks_by_source: dict[Path, dict[int, TextChunk]] = {}
    samples: list[dict[str, Any]] = []
    cases: dict[str, ExtractionSeedCase] = {}
    for item in payload["samples"]:
        source = PROJECT_ROOT / item["source"]
        if source not in chunks_by_source:
            chunks_by_source[source] = {
                chunk.ordinal: chunk for chunk in _chunks(source, target_tokens)
            }
        ordinal = int(item["chunk_ordinal"])
        chunk = chunks_by_source[source].get(ordinal)
        if chunk is None:
            raise ValueError(f"unknown_real_chunk:{item['id']}:{ordinal}")
        text = str(chunk.content)
        gold = item.get("gold")
        if gold is not None:
            cases[item["id"]] = ExtractionSeedCase.model_validate(
                {
                    "id": item["id"],
                    "text": text,
                    "slice_tags": item["focus"],
                    "severity": item.get("severity", "critical"),
                    **gold,
                }
            )
        samples.append(
            {
                "kind": "real",
                "id": item["id"],
                "text": text,
                "source": item["source"],
                "chunk_ordinal": ordinal,
                "chapter_ordinal": chunk.chapter_ordinal,
                "focus": item["focus"],
                "annotation_status": (
                    item.get("annotation_status", "unscored")
                    if gold is not None
                    else "unscored"
                ),
                "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            }
        )
    return samples, cases


def _load_seed_samples(path: Path) -> tuple[list[dict[str, Any]], dict[str, ExtractionSeedCase]]:
    dataset = load_extraction_seed_dataset(path)
    cases = {case.id: case for case in dataset.cases}
    return (
        [
            {
                "kind": "seed",
                "id": case.id,
                "text": case.text,
                "severity": case.severity,
                "focus": case.slice_tags,
                "text_sha256": hashlib.sha256(case.text.encode("utf-8")).hexdigest(),
            }
            for case in dataset.cases
        ],
        cases,
    )


def _contract_metrics(
    candidates: VisualCandidateExtractionResult,
    packet: Any,
) -> dict[str, Any]:
    generic_explicit_names = [
        entity.mention_quote
        for entity in candidates.entities
        if entity.mention_kind == "explicit_name"
        and entity.mention_quote.strip().casefold() in GENERIC_EXPLICIT_NAME_SURFACES
    ]
    non_asserted_candidates = [
        index
        for index, candidate in enumerate(candidates.visual_candidates)
        if candidate.epistemic_status not in {"asserted", "negated"}
    ]
    age_candidates = [
        candidate for candidate in candidates.visual_candidates if candidate.field_path == "age"
    ]
    age_candidates_with_signal = sum(
        any(signal.kind == "age" for signal in candidate.temporal_signals)
        for candidate in age_candidates
    )
    candidate_fingerprints = [
        (
            candidate.entity_ref,
            candidate.field_path,
            json.dumps(
                candidate.value,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                default=str,
            ),
            candidate.evidence_quote,
            candidate.epistemic_status,
        )
        for candidate in candidates.visual_candidates
    ]
    fact_keys = [
        fact.candidate_key
        or (
            fact.mention_id,
            fact.field_path,
            json.dumps(
                fact.value,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                default=str,
            ),
            fact.start,
            fact.end,
        )
        for fact in packet.facts
    ]
    asserted_quotes = {
        candidate.evidence_quote
        for candidate in candidates.visual_candidates
        if candidate.epistemic_status == "asserted"
    }
    deferred_quotes = {
        item.evidence_quote
        for item in candidates.deferred_items
        if item.evidence_quote is not None
    }
    warnings = list(packet.warnings)
    return {
        "entity_count": len(candidates.entities),
        "visual_candidate_count": len(candidates.visual_candidates),
        "grounded_fact_count": len(packet.facts),
        "temporal_signal_count": len(packet.temporal_signals),
        "deferred_count": len(candidates.deferred_items),
        "deferred_reasons": dict(Counter(item.reason_code for item in candidates.deferred_items)),
        "warning_count": len(warnings),
        "rejected_warning_count": sum("rejected_" in warning for warning in warnings),
        "generic_explicit_name_violations": generic_explicit_names,
        "non_asserted_candidate_indexes": non_asserted_candidates,
        "age_candidate_count": len(age_candidates),
        "age_candidate_with_signal_count": age_candidates_with_signal,
        "duplicate_visual_candidate_count": len(candidate_fingerprints)
        - len(set(candidate_fingerprints)),
        "duplicate_grounded_fact_count": len(fact_keys) - len(set(fact_keys)),
        "asserted_deferred_collision_count": len(asserted_quotes & deferred_quotes),
        "asserted_deferred_collision_quotes": sorted(asserted_quotes & deferred_quotes),
    }


async def _run_variant(
    provider: OpenAICompatibleExtractionProvider,
    sample: dict[str, Any],
    seed_cases: dict[str, ExtractionSeedCase],
) -> dict[str, Any]:
    text = str(sample["text"])
    detailed = await provider.extract_chunk_detailed(text)
    candidates = detailed.output
    packet = ground_visual_candidates(text, candidates, mention_id_prefix=sample["id"])
    adapted = adapt_visual_candidates(text, candidates)
    score = None
    if sample["id"] in seed_cases:
        score = evaluate_extraction_case(
            seed_cases[sample["id"]],
            adapted,
            candidates=candidates,
            packet=packet,
        ).model_dump(mode="json")
    return {
        "provider_version": provider.version,
        "metadata": detailed.metadata.model_dump(mode="json"),
        "candidates": candidates.model_dump(mode="json"),
        "grounded_packet": packet.model_dump(mode="json"),
        "adapted_result": adapted.model_dump(mode="json"),
        "contract_metrics": _contract_metrics(candidates, packet),
        "seed_score": score if sample["kind"] == "seed" else None,
        "real_audit_score": score if sample["kind"] == "real" else None,
    }


def _aggregate(records: list[dict[str, Any]], variant: str) -> dict[str, Any]:
    outputs = [record["variants"][variant] for record in records]
    seed_scores = [output["seed_score"] for output in outputs if output["seed_score"] is not None]
    real_scores = [
        output["real_audit_score"]
        for output in outputs
        if output["real_audit_score"] is not None
    ]
    usage = [output["metadata"]["usage"] for output in outputs]
    metrics = [output["contract_metrics"] for output in outputs]
    return {
        "call_count": len(outputs),
        "seed_case_count": len(seed_scores),
        "seed_pass": sum(score["status"] == "pass" for score in seed_scores),
        "seed_needs_review": sum(score["status"] == "needs_review" for score in seed_scores),
        "seed_fail": sum(score["status"] == "fail" for score in seed_scores),
        "seed_true_positive": sum(score["true_positive"] for score in seed_scores),
        "seed_false_positive": sum(score["false_positive"] for score in seed_scores),
        "seed_false_negative": sum(score["false_negative"] for score in seed_scores),
        "seed_allowed_observations": sum(
            score["allowed_observation_count"] for score in seed_scores
        ),
        "seed_forbidden_observations": sum(
            score["forbidden_observation_count"] for score in seed_scores
        ),
        "seed_mention_failures": sum(
            score["mention_failure_count"] for score in seed_scores
        ),
        "seed_deferred_failures": sum(
            score["deferred_failure_count"] for score in seed_scores
        ),
        "seed_temporal_failures": sum(
            score["temporal_failure_count"] for score in seed_scores
        ),
        "seed_duplicate_temporal_signals": sum(
            score["duplicate_temporal_signal_count"] for score in seed_scores
        ),
        "seed_asserted_deferred_collisions": sum(
            score["asserted_deferred_collision_count"] for score in seed_scores
        ),
        "real_audit_case_count": len(real_scores),
        "real_audit_pass": sum(score["status"] == "pass" for score in real_scores),
        "real_audit_needs_review": sum(
            score["status"] == "needs_review" for score in real_scores
        ),
        "real_audit_fail": sum(score["status"] == "fail" for score in real_scores),
        "real_audit_required_true_positive": sum(
            score["true_positive"] for score in real_scores
        ),
        "real_audit_required_false_negative": sum(
            score["false_negative"] for score in real_scores
        ),
        "real_audit_forbidden_observations": sum(
            score["forbidden_observation_count"] for score in real_scores
        ),
        "real_audit_ignored_unlisted_observations": sum(
            score["unlisted_observation_count"] for score in real_scores
        ),
        "real_audit_mention_failures": sum(
            score["mention_failure_count"] for score in real_scores
        ),
        "real_audit_deferred_failures": sum(
            score["deferred_failure_count"] for score in real_scores
        ),
        "real_audit_temporal_failures": sum(
            score["temporal_failure_count"] for score in real_scores
        ),
        "real_audit_duplicate_temporal_signals": sum(
            score["duplicate_temporal_signal_count"] for score in real_scores
        ),
        "real_audit_asserted_deferred_collisions": sum(
            score["asserted_deferred_collision_count"] for score in real_scores
        ),
        "input_tokens": sum(item["input_tokens"] for item in usage),
        "output_tokens": sum(item["output_tokens"] for item in usage),
        "reasoning_tokens": sum(item["reasoning_tokens"] for item in usage),
        "total_tokens": sum(item["total_tokens"] for item in usage),
        "latency_ms": sum(output["metadata"]["latency_ms"] for output in outputs),
        "visual_candidates": sum(item["visual_candidate_count"] for item in metrics),
        "grounded_facts": sum(item["grounded_fact_count"] for item in metrics),
        "deferred_items": sum(item["deferred_count"] for item in metrics),
        "warnings": sum(item["warning_count"] for item in metrics),
        "rejected_warnings": sum(item["rejected_warning_count"] for item in metrics),
        "generic_explicit_name_violations": sum(
            len(item["generic_explicit_name_violations"]) for item in metrics
        ),
        "non_asserted_candidates": sum(
            len(item["non_asserted_candidate_indexes"]) for item in metrics
        ),
        "age_candidates": sum(item["age_candidate_count"] for item in metrics),
        "age_candidates_with_signal": sum(
            item["age_candidate_with_signal_count"] for item in metrics
        ),
        "duplicate_visual_candidates": sum(
            item["duplicate_visual_candidate_count"] for item in metrics
        ),
        "duplicate_grounded_facts": sum(
            item["duplicate_grounded_fact_count"] for item in metrics
        ),
        "asserted_deferred_collisions": sum(
            item["asserted_deferred_collision_count"] for item in metrics
        ),
    }


async def run_ab(
    seed_path: Path,
    real_path: Path,
    output: Path,
    sample_ids: set[str] | None,
) -> None:
    seed_samples, seed_cases = _load_seed_samples(seed_path)
    real_samples, real_cases = _load_real_samples(real_path)
    scored_cases = {**seed_cases, **real_cases}
    samples = [*seed_samples, *real_samples]
    if sample_ids is not None:
        known_ids = {sample["id"] for sample in samples}
        missing = sorted(sample_ids - known_ids)
        if missing:
            raise ValueError(f"unknown_ab_sample_ids:{','.join(missing)}")
        samples = [sample for sample in samples if sample["id"] in sample_ids]
    providers = {
        "a": _provider(EXTRACTION_SYSTEM_PROMPT_V2_5, "visual-extraction-prompt-v2.5"),
        "b": _provider(EXTRACTION_SYSTEM_PROMPT_V2_6, "visual-extraction-prompt-v2.6"),
    }
    records: list[dict[str, Any]] = []
    for index, sample in enumerate(samples):
        order = ("a", "b") if index % 2 == 0 else ("b", "a")
        variants: dict[str, Any] = {}
        for variant in order:
            print(f"{sample['id']}:{variant}", flush=True)
            variants[variant] = await _run_variant(providers[variant], sample, scored_cases)
        records.append(
            {
                "sample": {key: value for key, value in sample.items() if key != "text"},
                "variants": variants,
            }
        )
    payload = {
        "experiment": "r1-prompt-v2.5-vs-v2.6",
        "execution": "alternating-order-one-call-per-sample-and-variant",
        "schema": providers["a"].version.split(":")[-2],
        "sample_count": len(samples),
        "seed_sample_count": len(seed_samples),
        "real_sample_count": len(real_samples),
        "aggregate": {
            "a": _aggregate(records, "a"),
            "b": _aggregate(records, "b"),
        },
        "records": records,
    }
    await asyncio.to_thread(output.parent.mkdir, parents=True, exist_ok=True)
    await asyncio.to_thread(
        output.write_text,
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload["aggregate"], ensure_ascii=False, indent=2))
    print(output)


def replay_report(
    seed_path: Path,
    real_path: Path,
    source_report: Path,
    output: Path,
) -> None:
    seed_samples, seed_cases = _load_seed_samples(seed_path)
    real_samples, real_cases = _load_real_samples(real_path)
    samples = {item["id"]: item for item in [*seed_samples, *real_samples]}
    scored_cases = {**seed_cases, **real_cases}
    payload = json.loads(source_report.read_text(encoding="utf-8"))
    previous_aggregate = payload.get("aggregate")
    records = payload["records"]
    for record in records:
        sample_id = record["sample"]["id"]
        if sample_id not in samples:
            raise ValueError(f"unknown_replay_sample:{sample_id}")
        sample = samples[sample_id]
        text = str(sample["text"])
        record["sample"] = {
            key: value for key, value in sample.items() if key != "text"
        }
        for variant in ("a", "b"):
            variant_output = record["variants"][variant]
            candidates = VisualCandidateExtractionResult.model_validate(
                variant_output["candidates"]
            )
            packet = ground_visual_candidates(
                text,
                candidates,
                mention_id_prefix=sample_id,
            )
            adapted = adapt_visual_candidates(text, candidates)
            score = evaluate_extraction_case(
                scored_cases[sample_id],
                adapted,
                candidates=candidates,
                packet=packet,
            ).model_dump(mode="json")
            variant_output["grounded_packet"] = packet.model_dump(mode="json")
            variant_output["adapted_result"] = adapted.model_dump(mode="json")
            variant_output["contract_metrics"] = _contract_metrics(candidates, packet)
            variant_output["seed_score"] = score if sample["kind"] == "seed" else None
            variant_output["real_audit_score"] = (
                score if sample["kind"] == "real" else None
            )
    seed_dataset = load_extraction_seed_dataset(seed_path)
    real_manifest = json.loads(real_path.read_text(encoding="utf-8"))
    payload["execution"] = "offline-rescore-from-saved-candidates"
    payload["source_report"] = str(source_report)
    payload["previous_aggregate"] = previous_aggregate
    payload["gold_dataset_version"] = seed_dataset.version
    payload["rubric_version"] = seed_dataset.rubric_version
    payload["real_manifest_version"] = real_manifest["version"]
    payload["aggregate"] = {
        "a": _aggregate(records, "a"),
        "b": _aggregate(records, "b"),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload["aggregate"], ensure_ascii=False, indent=2))
    print(output)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=Path, default=DEFAULT_SEED)
    parser.add_argument("--real", type=Path, default=DEFAULT_REAL)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sample-ids", type=_sample_ids)
    parser.add_argument("--replay-report", type=Path)
    args = parser.parse_args()
    if args.replay_report is not None:
        if args.sample_ids is not None:
            parser.error("--sample-ids cannot be combined with --replay-report")
        replay_report(args.seed, args.real, args.replay_report, args.output)
    else:
        asyncio.run(run_ab(args.seed, args.real, args.output, args.sample_ids))


if __name__ == "__main__":
    main()
