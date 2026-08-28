from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any

from novel_character_generator.application.ports.local_observation import (
    LocalObservationDiscoveryResult,
)
from novel_character_generator.application.services.local_observation_evaluation_service import (
    evaluate_local_observation_dataset,
    load_local_observation_evaluation_dataset,
)
from novel_character_generator.application.services.local_observation_service import (
    LocalObservationContractError,
    validate_local_observation_output,
)
from novel_character_generator.infrastructure.llm.local_observation import (
    OpenAICompatibleLocalObservationProvider,
)
from novel_character_generator.infrastructure.llm.openai_compatible import (
    ProviderExtractionError,
)
from novel_character_generator.settings import Settings


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


async def run(args: argparse.Namespace) -> int:
    dataset = load_local_observation_evaluation_dataset(args.dataset)
    if dataset.review_status != "approved":
        raise ValueError("m1_dataset_not_approved_for_real_run")
    settings = Settings()
    if settings.llm_provider == "mock":
        raise ValueError("real_m1_evaluation_requires_non_mock_provider")
    if settings.llm_api_key is None or settings.llm_model is None:
        raise ValueError("real_m1_evaluation_credentials_required")

    provider = OpenAICompatibleLocalObservationProvider(
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
        max_retries=settings.llm_max_retries,
    )
    started_at = datetime.now(UTC)
    output_dir = args.output_dir or (
        Path("data/diagnostics/m1-local-observation")
        / started_at.strftime("%Y%m%dT%H%M%SZ")
    )
    results_path = output_dir / "run.json"
    outputs_path = output_dir / "outputs.json"
    report_path = output_dir / "report.json"
    outputs: dict[str, LocalObservationDiscoveryResult] = {}
    records: list[dict[str, Any]] = []
    run_record: dict[str, Any] = {
        "run_schema_version": "m1-real-evaluation-run-v1",
        "started_at": started_at.isoformat(),
        "finished_at": None,
        "dataset": {
            "path": args.dataset.as_posix(),
            "version": dataset.dataset_version,
            "sha256": _sha256_file(args.dataset),
            "case_count": len(dataset.cases),
            "review_status": dataset.review_status,
        },
        "configuration": {
            "provider": settings.llm_provider,
            "model": settings.llm_model,
            "wire_api": settings.llm_wire_api,
            "thinking_enabled": settings.llm_thinking_enabled,
            "reasoning_effort": settings.llm_reasoning_effort,
            "max_output_tokens": settings.llm_max_output_tokens,
            "max_retries": settings.llm_max_retries,
            "prompt_version": provider.prompt_version,
            "prompt_hash": provider.prompt_hash,
            "model_config_version": provider.model_config_version,
            "raw_provider_response_capture": False,
        },
        "cases": records,
        "summary": None,
    }
    _write_json(results_path, run_record)

    for index, case in enumerate(dataset.cases, start=1):
        case_started = perf_counter()
        print(f"[{index}/{len(dataset.cases)}] {case.id}", flush=True)
        try:
            detailed = await provider.discover_detailed(case.input)
            contract_error: str | None = None
            try:
                validate_local_observation_output(case.input, detailed.output)
            except LocalObservationContractError as error:
                contract_error = error.code
            outputs[case.id] = detailed.output
            records.append(
                {
                    "case_id": case.id,
                    "status": "contract_failed" if contract_error else "succeeded",
                    "contract_error": contract_error,
                    "attempts": detailed.metadata.attempts,
                    "latency_ms": detailed.metadata.latency_ms,
                    "usage": detailed.metadata.usage.model_dump(mode="json"),
                    "provider_request_id": detailed.metadata.provider_request_id,
                    "response_model": detailed.metadata.response_model,
                    "elapsed_ms": (perf_counter() - case_started) * 1_000,
                }
            )
        except ProviderExtractionError as error:
            records.append(
                {
                    "case_id": case.id,
                    "status": "provider_failed",
                    "error_code": error.code,
                    "retryable": error.retryable,
                    "attempts": error.attempts,
                    "elapsed_ms": (perf_counter() - case_started) * 1_000,
                }
            )
        _write_json(
            outputs_path,
            {case_id: output.model_dump(mode="json") for case_id, output in outputs.items()},
        )
        _write_json(results_path, run_record)

    run_record["finished_at"] = datetime.now(UTC).isoformat()
    if len(outputs) == len(dataset.cases):
        report = evaluate_local_observation_dataset(dataset, outputs)
        _write_json(report_path, report.model_dump(mode="json"))
        total_usage = {
            key: sum(
                int(record.get("usage", {}).get(key, 0))
                for record in records
                if isinstance(record.get("usage"), dict)
            )
            for key in (
                "input_tokens",
                "cache_hit_tokens",
                "cache_miss_tokens",
                "reasoning_tokens",
                "output_tokens",
                "total_tokens",
            )
        }
        run_record["summary"] = {
            "completed_cases": len(outputs),
            "failed_cases": 0,
            "total_attempts": sum(int(record.get("attempts", 0)) for record in records),
            "usage": total_usage,
            "report": report.model_dump(mode="json", exclude={"cases"}),
        }
        exit_code = 0
    else:
        run_record["summary"] = {
            "completed_cases": len(outputs),
            "failed_cases": len(dataset.cases) - len(outputs),
            "total_attempts": sum(int(record.get("attempts", 0)) for record in records),
        }
        exit_code = 2
    _write_json(results_path, run_record)
    print(results_path, flush=True)
    return exit_code


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the approved M1 dataset against the configured real LLM provider."
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("tests/evaluation/m1_local_observation_discovery_v1.json"),
    )
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args()
    raise SystemExit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
