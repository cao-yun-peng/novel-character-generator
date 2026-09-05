"""Offline verification of API outputs, usage and snapshot consumption."""
import collections
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
from novel_character_generator.__main__ import _read_utf8_text
from novel_character_generator.automatic_semantics import run_automatic_semantics, validate_automatic_semantics
from novel_character_generator.character_snapshot import build_character_snapshot
from jsonschema import Draft202012Validator


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    output = ROOT / "runs/semantic-dev30/douluo-live"
    if len(sys.argv) > 1:
        output = ROOT / sys.argv[1]
    run = ROOT / "runs/douluo-20ch-e2e-dev13-20260831"
    source = dict(
        document_text=_read_utf8_text(ROOT / "tests/小说/斗罗大陆前20章.txt"),
        fact_groups=read(run / "post-link-fact-groups-dev18/document-character-fact-groups.json"),
        appearance_states=read(run / "snapshots-dev29/document-character-appearance-states.json"),
        label_projection=read(run / "label-review-projection-dev25/document-character-label-review-projection.json"),
        chunk_manifest=read(run / "m1/manifest.json"),
    )
    if "--replay" in sys.argv:
        run_automatic_semantics(**source, output_dir=output,
                               replay_dir=ROOT / "runs/semantic-dev30/douluo-live", max_new_calls=0)
    artifact = read(output / "automatic-semantics.json")
    manifest = read(output / "manifest.json")
    model_events, model_relations, rejected = [], [], []
    for task in manifest["tasks"]:
        path = output / "tasks" / (task["task_id"] + ".json")
        if not path.exists():
            continue
        raw = read(path)["model_output"]
        raw = json.loads(raw) if isinstance(raw, str) else raw
        if task["kind"] == "events":
            model_events.extend({"task_id": task["task_id"], **event} for event in raw.get("events", []))
        else:
            model_relations.append({"task_id": task["task_id"], "facts": task["payload"], **raw})
    for item in artifact["reviews"]:
        path = output / "tasks" / (item["task_id"] + ".json")
        raw = read(path)["model_output"] if path.exists() else None
        raw = json.loads(raw) if isinstance(raw, str) else raw
        rejected.append({**item, "model_item": raw["events"][item["item_index"]]
                         if raw and "item_index" in item else raw})
    traces = []
    for path in (ROOT / "runs/semantic-dev30").glob("douluo-live*/live-provider-traces.jsonl"):
        traces.extend(json.loads(line) for line in path.read_text("utf-8").splitlines() if line.strip())
    report = {
        "summary": read(output / "summary.json"),
        "model_event_counts": dict(collections.Counter(e["kind"] for e in model_events)),
        "accepted_event_counts": dict(collections.Counter(e["kind"] for e in artifact["events"])),
        "model_relation_counts": dict(collections.Counter(e["relation"] for e in model_relations)),
        "accepted_relation_counts": dict(collections.Counter(e["relation"] for e in artifact["relations"])),
        "review_counts": dict(collections.Counter(e["message"] for e in artifact["reviews"])),
        "api_traces": len(traces), "http_attempts": sum(t["attempts"] for t in traces),
        "successful_calls": sum(t["success"] for t in traces),
        "failed_calls": sum(not t["success"] for t in traces),
        "known_usage": {key: sum(t["usage"].get(key) or 0 for t in traces)
                        for key in ("input_tokens", "output_tokens", "reasoning_tokens", "cached_input_tokens", "total_tokens")},
        "unknown_usage_calls": sum(t["usage"].get("total_tokens") is None for t in traces),
    }
    write(output / "model-event-audit.json", model_events)
    write(output / "model-relation-audit.json", model_relations)
    write(output / "rejected-output-audit.json", rejected)
    if artifact["complete"]:
        schema = read(ROOT / "docs/contracts/simplified-character-evidence-v3-model-schemas.json")
        def validate(name, value):
            Draft202012Validator({"$ref": "#/$defs/" + name, "$defs": schema["$defs"]}).validate(value)
        validate("AutomaticSemantics", artifact)
        validate_automatic_semantics(artifact, document_text=source["document_text"], fact_groups=source["fact_groups"],
                                    facts={f["canonical_fact_id"]: f for f in source["fact_groups"]["fact_groups"]})
        snapshots = []
        for request in read(run / "render-profiles-dev26/render-profile-requests.json")["requests"]:
            snapshot = build_character_snapshot(
                **{k: v for k, v in source.items() if k != "chunk_manifest"},
                run_id=output.name, character_id=request["character_id"], **request["selector"],
                automatic_semantics=artifact, explain=True,
            )
            validate("CharacterSnapshot", snapshot)
            snapshots.append(snapshot)
        write(output / "verified-snapshots.json", snapshots)
        report["snapshots"] = len(snapshots)
        report["snapshot_conflicts"] = sum(len(s["unresolved_conflicts"]) for s in snapshots)
        report["schema_and_reground_valid"] = True
    write(output / "verification-report.json", report)
    print(json.dumps(report, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
