from __future__ import annotations

import argparse
import json
from pathlib import Path

from novel_character_generator.application.services.field_disambiguation_evaluation_service import (
    evaluate_field_disambiguation_dataset,
    load_field_disambiguation_evaluation_dataset,
    load_field_disambiguation_outputs,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate saved M2 field-disambiguation outputs")
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--outputs", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    dataset = load_field_disambiguation_evaluation_dataset(args.dataset)
    outputs = load_field_disambiguation_outputs(args.outputs)
    report = evaluate_field_disambiguation_dataset(dataset, outputs)
    rendered = json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2)
    if args.report is not None:
        args.report.write_text(f"{rendered}\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
