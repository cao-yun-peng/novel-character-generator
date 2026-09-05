"""User-authorized 52-task live test; credentials never enter logs."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
from novel_character_generator.__main__ import _load_deepseek_env_file, _read_utf8_text
from novel_character_generator.automatic_semantics import run_automatic_semantics
from novel_character_generator.providers import DeepSeekProvider


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    output = ROOT / "runs/semantic-dev30/douluo-live"
    output.mkdir(parents=True, exist_ok=True)
    trace_path = output / "live-provider-traces.jsonl"
    count = 0

    def trace_sink(trace):
        nonlocal count
        count += 1
        value = trace.to_dict()
        with trace_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(value, ensure_ascii=False) + "\n")
        print(json.dumps({"call": count, "success": trace.success, "duration_ms": trace.duration_ms,
                          "error_kind": trace.error_kind}, ensure_ascii=False), flush=True)

    _load_deepseek_env_file(ROOT / ".env")
    provider = DeepSeekProvider.from_env(trace_sink=trace_sink)
    run = ROOT / "runs/douluo-20ch-e2e-dev13-20260831"
    result = run_automatic_semantics(
        document_text=_read_utf8_text(ROOT / "tests/小说/斗罗大陆前20章.txt"),
        fact_groups=read(run / "post-link-fact-groups-dev18/document-character-fact-groups.json"),
        appearance_states=read(run / "snapshots-dev29/document-character-appearance-states.json"),
        label_projection=read(run / "label-review-projection-dev25/document-character-label-review-projection.json"),
        chunk_manifest=read(run / "m1/manifest.json"), output_dir=output, provider=provider, max_new_calls=52,
    )
    print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
