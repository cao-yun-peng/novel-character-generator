from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any, Literal

from pydantic import BaseModel, Field

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
from novel_character_generator.infrastructure.llm.structured_client import (
    ProviderExtractionError,
)


class EvaluationModelConfig(BaseModel):
    provider: Literal["deepseek", "openai_compatible"]
    api_key: str = Field(min_length=1)
    base_url: str = "https://api.deepseek.com"
    model: str = Field(min_length=1)
    timeout_seconds: float = Field(default=180.0, gt=0)
    wire_api: Literal["chat_completions", "responses"] = "chat_completions"
    thinking_enabled: bool = False
    reasoning_effort: Literal["none", "low", "medium", "high"] = "none"
    max_output_tokens: int = Field(default=8_192, ge=256, le=65_536)
    total_deadline_seconds: float = Field(default=120.0, gt=0)
    max_retries: int = Field(default=1, ge=0, le=3)

    @classmethod
    def from_environment(cls) -> EvaluationModelConfig:
        return cls.model_validate(
            {
                "provider": os.getenv("LLM_PROVIDER"),
                "api_key": os.getenv("LLM_API_KEY"),
                "base_url": os.getenv("LLM_BASE_URL", "https://api.deepseek.com"),
                "model": os.getenv("LLM_MODEL"),
                "timeout_seconds": os.getenv("LLM_TIMEOUT_SECONDS", "180"),
                "wire_api": os.getenv("LLM_WIRE_API", "chat_completions"),
                "thinking_enabled": os.getenv("LLM_THINKING_ENABLED", "false"),
                "reasoning_effort": os.getenv("LLM_REASONING_EFFORT", "none"),
                "max_output_tokens": os.getenv("LLM_MAX_OUTPUT_TOKENS", "8192"),
                "total_deadline_seconds": os.getenv("LLM_TOTAL_DEADLINE_SECONDS", "120"),
                "max_retries": os.getenv("LLM_MAX_RETRIES", "1"),
            }
        )


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
    if dataset.review_status != "approved" and not args.allow_draft_diagnostic:
        raise ValueError("m1_dataset_not_approved_for_real_run")
    settings = EvaluationModelConfig.from_environment()
    if args.case_id:
        requested_case_ids = set(args.case_id)
        known_case_ids = {case.id for case in dataset.cases}
        unknown_case_ids = requested_case_ids - known_case_ids
        if unknown_case_ids:
            raise ValueError(f"m1_unknown_case_ids:{','.join(sorted(unknown_case_ids))}")
        dataset = dataset.model_copy(
            update={"cases": [case for case in dataset.cases if case.id in requested_case_ids]}
        )

    effective_max_retries = min(settings.max_retries, 1)
    provider = OpenAICompatibleLocalObservationProvider(
        provider=settings.provider,
        base_url=settings.base_url,
        api_key=settings.api_key,
        model=settings.model,
        timeout_seconds=settings.timeout_seconds,
        wire_api=settings.wire_api,
        thinking_enabled=settings.thinking_enabled,
        reasoning_effort=settings.reasoning_effort,
        max_output_tokens=settings.max_output_tokens,
        total_deadline_seconds=settings.total_deadline_seconds,
        max_retries=effective_max_retries,
    )
    if dataset.prompt_version != provider.prompt_version:
        raise ValueError("m1_dataset_prompt_version_mismatch")
    started_at = datetime.now(UTC)
    output_dir = args.output_dir or (
        Path("data/diagnostics/m1-local-observation") / started_at.strftime("%Y%m%dT%H%M%SZ")
    )
    results_path = output_dir / "run.json"
    outputs_path = output_dir / "outputs.json"
    report_path = output_dir / "report.json"
    outputs: dict[str, LocalObservationDiscoveryResult] = {}
    records: list[dict[str, Any]] = []
    run_record: dict[str, Any] = {
        "run_schema_version": "m1-real-evaluation-run-v1",
        "run_mode": (
            "quality_gate"
            if dataset.review_status == "approved"
            else "draft_development_diagnostic"
        ),
        "started_at": started_at.isoformat(),
        "finished_at": None,
        "dataset": {
            "path": args.dataset.as_posix(),
            "version": dataset.dataset_version,
            "sha256": _sha256_file(args.dataset),
            "case_count": len(dataset.cases),
            "selected_case_ids": [case.id for case in dataset.cases],
            "review_status": dataset.review_status,
        },
        "configuration": {
            "provider": settings.provider,
            "model": settings.model,
            "wire_api": settings.wire_api,
            "thinking_enabled": settings.thinking_enabled,
            "reasoning_effort": settings.reasoning_effort,
            "max_output_tokens": settings.max_output_tokens,
            "configured_max_retries": settings.max_retries,
            "max_retries": effective_max_retries,
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
        description=(
            "Run an approved M1 quality dataset, or an explicitly allowed draft "
            "development diagnostic, against the configured real LLM provider."
        )
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("tests/evaluation/m1_local_observation_discovery_v1.json"),
    )
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument(
        "--case-id",
        action="append",
        default=[],
        help="Run only this case ID; repeat the option to select multiple cases.",
    )
    parser.add_argument(
        "--allow-draft-diagnostic",
        action="store_true",
        help=(
            "Allow a draft dataset only as a recorded development diagnostic; "
            "this does not approve its labels or make the run a quality gate."
        ),
    )
    args = parser.parse_args()
    raise SystemExit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
