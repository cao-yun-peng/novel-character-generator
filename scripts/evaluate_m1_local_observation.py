from __future__ import annotations

import argparse
from pathlib import Path

from novel_character_generator.application.ports.local_observation import (
    LocalObservationDiscoveryResult,
)
from novel_character_generator.application.services.local_observation_evaluation_service import (
    evaluate_local_observation_dataset,
    load_local_observation_evaluation_dataset,
    load_outputs_by_case_id,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Offline-score saved M1 outputs; this never calls a model provider."
    )
    parser.add_argument(
        "outputs",
        type=Path,
        nargs="+",
        help=(
            "One or more JSON objects keyed by M1 evaluation case id; later files "
            "replace earlier cases for bounded retry/resume scoring."
        ),
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("tests/evaluation/m1_local_observation_discovery_v1.json"),
    )
    parser.add_argument("--report", type=Path, default=None)
    args = parser.parse_args()

    dataset = load_local_observation_evaluation_dataset(args.dataset)
    outputs: dict[str, LocalObservationDiscoveryResult] = {}
    for path in args.outputs:
        outputs.update(load_outputs_by_case_id(path))
    report = evaluate_local_observation_dataset(dataset, outputs)
    rendered = report.model_dump_json(indent=2)
    if args.report is not None:
        args.report.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)


if __name__ == "__main__":
    main()
