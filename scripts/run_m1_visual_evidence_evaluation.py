from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from novel_character_generator.application.ports.model_provider import ModelCallMetadata
from novel_character_generator.application.ports.visual_evidence import (
    VISUAL_EVIDENCE_SOURCE_MATCH_POLICY_VERSION,
    VisualEvidenceDiscoveryResult,
    VisualEvidenceExecutionRequest,
    VisualEvidenceProvider,
)
from novel_character_generator.application.services.visual_evidence_evaluation_service import (
    M1_V2_EVALUATION_RUBRIC_VERSION,
    VisualEvidenceEvaluationDataset,
    evaluate_visual_evidence_dataset,
    load_outputs_by_case_id,
    load_visual_evidence_evaluation_dataset,
)
from novel_character_generator.application.services.visual_evidence_service import (
    VisualEvidenceContractError,
    VisualEvidenceShadowService,
)
from novel_character_generator.infrastructure.llm.structured_client import (
    ProviderExtractionError,
)
from novel_character_generator.infrastructure.llm.visual_evidence import (
    OpenAICompatibleVisualEvidenceProvider,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUBRIC_IMPLEMENTATION_PATH = (
    PROJECT_ROOT
    / "src/novel_character_generator/application/services/visual_evidence_evaluation_service.py"
)
VALIDATION_IMPLEMENTATION_PATH = (
    PROJECT_ROOT
    / "src/novel_character_generator/application/services/visual_evidence_service.py"
)
EVALUATION_DATA_POLICY_VERSION = "m1-visual-evidence-evaluation-data-policy-v1"
RUN_MANIFEST_SCHEMA_VERSION = "m1-visual-evidence-evaluation-run-v1"


class EvaluationModelConfig(BaseModel):
    provider: Literal["deepseek", "openai_compatible"]
    api_key: str = Field(min_length=1)
    base_url: str = "https://api.deepseek.com"
    model: str = Field(min_length=1)
    wire_api: Literal["chat_completions", "responses"] = "chat_completions"
    reasoning_effort: Literal["none", "low", "medium", "high"] = "none"
    max_output_tokens: int = Field(default=4_096, ge=256, le=65_536)

    @classmethod
    def from_environment(cls) -> EvaluationModelConfig:
        _load_dotenv()
        return cls.model_validate(
            {
                "provider": os.getenv("LLM_PROVIDER"),
                "api_key": os.getenv("LLM_API_KEY"),
                "base_url": os.getenv("LLM_BASE_URL", "https://api.deepseek.com"),
                "model": os.getenv("LLM_MODEL"),
                "wire_api": os.getenv("LLM_WIRE_API", "chat_completions"),
                "reasoning_effort": os.getenv("LLM_REASONING_EFFORT", "none"),
                "max_output_tokens": os.getenv("LLM_MAX_OUTPUT_TOKENS", "4096"),
            }
        )


def _load_dotenv(path: Path = Path(".env")) -> None:
    """Load local development settings without overriding explicit process env vars."""

    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ.setdefault(name, value)


def _sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


async def execute_dataset(
    dataset: VisualEvidenceEvaluationDataset,
    provider: VisualEvidenceProvider,
    *,
    run_id: str,
    source_document_version_id: str,
    evaluation_attempt_id: str,
    wire_api: Literal["chat_completions", "responses"] = "chat_completions",
) -> tuple[dict[str, object], list[dict[str, object]]]:
    """Run every case through the same deterministic shadow boundary used by M1."""

    service = VisualEvidenceShadowService(provider)
    outputs: dict[str, object] = {}
    case_runs: list[dict[str, object]] = []
    for case in dataset.cases:
        print(f"running {case.id}", flush=True)
        try:
            artifact = await service.run(
                VisualEvidenceExecutionRequest(
                    run_id=run_id,
                    source_document_version_id=source_document_version_id,
                    data_policy_version=EVALUATION_DATA_POLICY_VERSION,
                    evaluation_attempt_id=evaluation_attempt_id,
                    payload=case.input,
                )
            )
        except VisualEvidenceContractError as error:
            failed_output = error.output
            failed_metadata = error.metadata
            input_fingerprint = error.input_fingerprint
            output_fingerprint = error.output_fingerprint
            if (
                failed_output is None
                or failed_metadata is None
                or input_fingerprint is None
                or output_fingerprint is None
            ):
                raise
            outputs[case.id] = failed_output.model_dump(mode="json")
            case_runs.append(
                {
                    "case_id": case.id,
                    "status": "deterministic_validation_failed",
                    "reason_codes": [error.code],
                    "input_fingerprint": input_fingerprint,
                    "output_fingerprint": output_fingerprint,
                    "usage": failed_metadata.model_dump(mode="json"),
                }
            )
            continue
        except ProviderExtractionError as error:
            failed_output = VisualEvidenceDiscoveryResult(
                schema_version="visual-evidence-discovery-v2",
                chunk_id=case.input.chunk_id,
                mentions=(),
                evidence_candidates=(),
            )
            outputs[case.id] = failed_output.model_dump(mode="json")
            case_runs.append(
                {
                    "case_id": case.id,
                    "status": "provider_failed",
                    "reason_codes": [error.code],
                    "input_fingerprint": None,
                    "output_fingerprint": None,
                    "usage": ModelCallMetadata(
                        wire_api=wire_api,
                        status="provider_failed",
                        finish_reason=error.code,
                        attempts=error.attempts,
                        latency_ms=0,
                    ).model_dump(mode="json"),
                }
            )
            continue
        outputs[case.id] = artifact.output.model_dump(mode="json")
        case_runs.append(
            {
                "case_id": case.id,
                "status": artifact.status,
                "reason_codes": list(artifact.reason_codes),
                "input_fingerprint": artifact.input_fingerprint,
                "output_fingerprint": artifact.output_fingerprint,
                "usage": artifact.usage.model_dump(mode="json"),
            }
        )
    return outputs, case_runs


async def run(args: argparse.Namespace) -> int:
    started_at = _utc_now()
    dataset_path = args.dataset.resolve()
    output_path = args.output.resolve()
    report_path = args.report.resolve() if args.report is not None else None
    manifest_path = args.run_manifest.resolve()
    dataset = load_visual_evidence_evaluation_dataset(
        dataset_path,
        project_root=PROJECT_ROOT,
    )
    if dataset.review_status != "approved" and not args.allow_draft_diagnostic:
        raise ValueError("m1_visual_evidence_dataset_not_approved_for_real_run")
    settings = EvaluationModelConfig.from_environment()
    provider = OpenAICompatibleVisualEvidenceProvider(
        provider=settings.provider,
        base_url=settings.base_url,
        api_key=settings.api_key,
        model=settings.model,
        wire_api=settings.wire_api,
        reasoning_effort=settings.reasoning_effort,
        max_output_tokens=settings.max_output_tokens,
    )
    if dataset.prompt_version != provider.prompt_version:
        raise ValueError("m1_visual_evidence_prompt_version_mismatch")

    dataset_sha256 = _sha256_path(dataset_path)
    rubric_sha256 = _sha256_path(RUBRIC_IMPLEMENTATION_PATH)
    run_id = args.run_id or f"m1-eval-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}"
    evaluation_attempt_id = args.evaluation_attempt_id or f"{run_id}-attempt-1"
    source_document_version_id = (
        f"dataset:{dataset.dataset_version}:{dataset_sha256[:16]}"
    )
    outputs, case_runs = await execute_dataset(
        dataset,
        provider,
        run_id=run_id,
        source_document_version_id=source_document_version_id,
        evaluation_attempt_id=evaluation_attempt_id,
        wire_api=settings.wire_api,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(outputs, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    report = evaluate_visual_evidence_dataset(
        dataset,
        load_outputs_by_case_id(output_path),
    )
    if report_path is not None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")

    manifest = {
        "schema_version": RUN_MANIFEST_SCHEMA_VERSION,
        "run_id": run_id,
        "evaluation_attempt_id": evaluation_attempt_id,
        "started_at": started_at,
        "finished_at": _utc_now(),
        "dataset": {
            "path": dataset_path.relative_to(PROJECT_ROOT).as_posix(),
            "version": dataset.dataset_version,
            "review_status": dataset.review_status,
            "sha256": dataset_sha256,
        },
        "rubric": {
            "version": M1_V2_EVALUATION_RUBRIC_VERSION,
            "implementation_path": RUBRIC_IMPLEMENTATION_PATH.relative_to(
                PROJECT_ROOT
            ).as_posix(),
            "sha256": rubric_sha256,
        },
        "deterministic_validation": {
            "source_match_policy_version": (
                VISUAL_EVIDENCE_SOURCE_MATCH_POLICY_VERSION
            ),
            "implementation_path": VALIDATION_IMPLEMENTATION_PATH.relative_to(
                PROJECT_ROOT
            ).as_posix(),
            "sha256": _sha256_path(VALIDATION_IMPLEMENTATION_PATH),
        },
        "prompt": {
            "version": provider.prompt_version,
            "sha256": provider.prompt_hash,
        },
        "model": {
            "provider": settings.provider,
            "requested_model": settings.model,
            "wire_api": settings.wire_api,
            "reasoning_effort": settings.reasoning_effort,
            "max_output_tokens": settings.max_output_tokens,
            "model_config_version": provider.model_config_version,
        },
        "data_policy_version": EVALUATION_DATA_POLICY_VERSION,
        "case_count": len(dataset.cases),
        "case_runs": case_runs,
        "artifacts": {
            "outputs": {
                "path": output_path.relative_to(PROJECT_ROOT).as_posix(),
                "sha256": _sha256_path(output_path),
            },
            "report": (
                {
                    "path": report_path.relative_to(PROJECT_ROOT).as_posix(),
                    "sha256": _sha256_path(report_path),
                }
                if report_path is not None
                else None
            ),
        },
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Run M1 v2 visual evidence evaluation.")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("tests/evaluation/m1_visual_evidence_discovery_v2.json"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/diagnostics/m1-v2.5/outputs.json"),
    )
    parser.add_argument("--report", type=Path, default=None)
    parser.add_argument(
        "--run-manifest",
        type=Path,
        default=Path("data/diagnostics/m1-v2.5/run.json"),
    )
    parser.add_argument("--run-id", type=str, default=None)
    parser.add_argument("--evaluation-attempt-id", type=str, default=None)
    parser.add_argument("--allow-draft-diagnostic", action="store_true")
    raise SystemExit(asyncio.run(run(parser.parse_args())))


if __name__ == "__main__":
    main()
