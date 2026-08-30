from __future__ import annotations

import argparse
from pathlib import Path

from novel_character_generator.application.services.visual_evidence_evaluation_service import (
    evaluate_visual_evidence_dataset,
    load_outputs_by_case_id,
    load_visual_evidence_evaluation_dataset,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Offline-score saved M1 v2 evidence outputs; never calls a model provider."
    )
    parser.add_argument(
        "outputs",
        type=Path,
        nargs="+",
        help="JSON objects keyed by M1 v2 evaluation case id; later files replace earlier cases.",
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("tests/evaluation/m1_visual_evidence_discovery_v2.json"),
    )
    parser.add_argument("--report", type=Path, default=None)
    args = parser.parse_args()

    dataset = load_visual_evidence_evaluation_dataset(
        args.dataset,
        project_root=Path.cwd(),
    )
    outputs = {}
    for path in args.outputs:
        outputs.update(load_outputs_by_case_id(path))
    report = evaluate_visual_evidence_dataset(dataset, outputs)
    rendered = report.model_dump_json(indent=2)
    if args.report is not None:
        args.report.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)


if __name__ == "__main__":
    main()
