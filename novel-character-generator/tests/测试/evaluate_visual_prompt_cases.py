r"""Run selected visual seed cases independently through the production v3 path."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from novel_character_generator.application.ports.extraction import (  # noqa: E402
    GroundedVisualExtractionResult,
    VisualCandidateExtractionResult,
)
from novel_character_generator.application.services.extraction_evaluation_service import (  # noqa: E402
    evaluate_extraction_case,
    load_extraction_seed_dataset,
)
from novel_character_generator.application.services.visual_candidate_adapter import (  # noqa: E402
    adapt_visual_candidates,
    ground_visual_candidates,
)
from novel_character_generator.infrastructure.llm.openai_compatible import (  # noqa: E402
    OpenAICompatibleExtractionProvider,
)
from novel_character_generator.workers.main import extraction_provider  # noqa: E402

DEFAULT_DATASET = PROJECT_ROOT / "tests" / "evaluation" / "visual_extraction_seed_v1.json"


def _case_ids(value: str) -> list[str]:
    ids = [item.strip() for item in value.split(",") if item.strip()]
    if not ids:
        raise argparse.ArgumentTypeError("at least one case id is required")
    if len(ids) != len(set(ids)):
        raise argparse.ArgumentTypeError("case ids must be unique")
    return ids


def _write_json(output: Path, payload: object) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


async def evaluate_cases(
    dataset_path: Path,
    case_ids: list[str],
    output: Path,
) -> None:
    dataset = load_extraction_seed_dataset(dataset_path)
    by_id = {case.id: case for case in dataset.cases}
    missing = sorted(set(case_ids) - set(by_id))
    if missing:
        raise ValueError(f"unknown_seed_case_ids:{','.join(missing)}")

    provider = extraction_provider()
    records: list[dict[str, object]] = []
    status_counts = {"pass": 0, "needs_review": 0, "fail": 0}
    for case_id in case_ids:
        case = by_id[case_id]
        if isinstance(provider, OpenAICompatibleExtractionProvider):
            detailed = await provider.extract_chunk_detailed(case.text)
            candidates = detailed.output
            metadata: object = detailed.metadata.model_dump(mode="json")
        else:
            candidates = await provider.extract_chunk(case.text)
            metadata = {"provider": "mock"}
        grounded = adapt_visual_candidates(case.text, candidates)
        packet = ground_visual_candidates(case.text, candidates, mention_id_prefix=case.id)
        score = evaluate_extraction_case(
            case,
            grounded,
            candidates=candidates,
            packet=packet,
        )
        status_counts[score.status] += 1
        records.append(
            {
                "case": case.model_dump(mode="json"),
                "provider_metadata": metadata,
                "visual_candidates": candidates.model_dump(mode="json"),
                "grounded_candidate_packet": packet.model_dump(mode="json"),
                "grounded_visual_result": grounded.model_dump(mode="json"),
                "score": score.model_dump(mode="json"),
            }
        )
        print(f"{case_id}: {score.status}")

    payload = {
        "dataset": {
            "name": dataset.name,
            "version": dataset.version,
            "rubric_version": dataset.rubric_version,
        },
        "provider_version": provider.version,
        "execution_mode": "one_provider_call_per_case",
        "case_count": len(records),
        "passed_case_count": status_counts["pass"],
        "needs_review_case_count": status_counts["needs_review"],
        "failed_case_count": status_counts["fail"],
        "records": records,
    }
    await asyncio.to_thread(_write_json, output, payload)
    print(output)


def rescore_report(dataset_path: Path, report_path: Path, output: Path) -> None:
    dataset = load_extraction_seed_dataset(dataset_path)
    by_id = {case.id: case for case in dataset.cases}
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if not isinstance(report, dict) or not isinstance(report.get("records"), list):
        raise ValueError("invalid_visual_evaluation_report")

    records: list[dict[str, object]] = []
    status_counts = {"pass": 0, "needs_review": 0, "fail": 0}
    for raw_record in report["records"]:
        if not isinstance(raw_record, dict):
            raise ValueError("invalid_visual_evaluation_record")
        raw_case = raw_record.get("case")
        if not isinstance(raw_case, dict) or not isinstance(raw_case.get("id"), str):
            raise ValueError("missing_visual_evaluation_case_id")
        case_id = raw_case["id"]
        if case_id not in by_id:
            raise ValueError(f"unknown_seed_case_id:{case_id}")
        grounded = GroundedVisualExtractionResult.model_validate(
            raw_record.get("grounded_visual_result")
        )
        raw_candidates = raw_record.get("visual_candidates")
        candidates = (
            VisualCandidateExtractionResult.model_validate(raw_candidates)
            if raw_candidates is not None
            else None
        )
        packet = (
            ground_visual_candidates(
                by_id[case_id].text,
                candidates,
                mention_id_prefix=case_id,
            )
            if candidates is not None
            else None
        )
        score = evaluate_extraction_case(
            by_id[case_id],
            grounded,
            candidates=candidates,
            packet=packet,
        )
        status_counts[score.status] += 1
        records.append(
            {
                "case_id": case_id,
                "score": score.model_dump(mode="json"),
            }
        )
        print(f"{case_id}: {score.status}")

    payload = {
        "dataset": {
            "name": dataset.name,
            "version": dataset.version,
            "rubric_version": dataset.rubric_version,
        },
        "source_report": str(report_path),
        "source_provider_version": report.get("provider_version"),
        "execution_mode": "offline_rescore",
        "case_count": len(records),
        "passed_case_count": status_counts["pass"],
        "needs_review_case_count": status_counts["needs_review"],
        "failed_case_count": status_counts["fail"],
        "records": records,
    }
    _write_json(output, payload)
    print(output)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--case-ids", type=_case_ids)
    mode.add_argument("--replay-report", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.replay_report is not None:
        rescore_report(args.dataset, args.replay_report, args.output)
    else:
        asyncio.run(evaluate_cases(args.dataset, args.case_ids, args.output))


if __name__ == "__main__":
    main()
