"""Reproduce the dev29 snapshot smoke test without touching source runs."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
from jsonschema import Draft202012Validator
from novel_character_generator.appearance_semantic_relations import build_appearance_semantic_projection
from novel_character_generator.character_snapshot import build_character_snapshot, build_render_ready_character_profiles


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="")


def main():
    run = ROOT / "runs/douluo-20ch-e2e-dev13-20260831"
    paths = [
        run / "post-link-fact-groups-dev18/document-character-fact-groups.json",
        run / "appearance-transitions-dev24/document-character-appearance-states.json",
        run / "label-review-projection-dev25/document-character-label-review-projection.json",
        run / "render-profiles-dev26/render-profile-requests.json",
        run / "render-profiles-dev26/render-ready-character-profiles.json",
        ROOT / "tests/小说/斗罗大陆前20章.txt",
    ]
    before = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    groups, states, labels, requests, old_profiles = [read(p) for p in paths[:5]]
    with paths[-1].open(encoding="utf-8-sig", newline="") as stream:
        text = stream.read()
    # Upgrade only the deterministic relation projection; keep old state sources immutable.
    semantic = build_appearance_semantic_projection(
        source_document_version_id=groups["source_document_version_id"], document_length=len(text),
        fact_groups=groups, fact_assignments=states["fact_assignments"], state_segments=states["state_segments"],
    )
    states.update({k: v for k, v in semantic.items() if k != "summary"})
    states["summary"].update(semantic["summary"])
    schema = read(ROOT / "docs/contracts/simplified-character-evidence-v3-model-schemas.json")
    Draft202012Validator.check_schema(schema)

    def validate(name, value):
        Draft202012Validator({"$ref": "#/$defs/" + name, "$defs": schema["$defs"]}).validate(value)

    validate("LegacyRenderReadyCharacterProfilesV1", old_profiles)
    snapshots = []
    for request in requests["requests"]:
        args = dict(document_text=text, fact_groups=groups, appearance_states=states, label_projection=labels,
                    run_id="douluo-snapshot-dev29", character_id=request["character_id"],
                    **request["selector"], explain=True)
        snapshot = build_character_snapshot(**args)
        assert snapshot == build_character_snapshot(**args)
        validate("CharacterSnapshot", snapshot)
        assert snapshot["compile_status"] in {"compiled", "compiled_with_warnings"}
        snapshots.append(snapshot)
    profiles = build_render_ready_character_profiles(
        document_text=text, fact_groups=groups, appearance_states=states, label_projection=labels,
        requests=requests["requests"],
    )
    validate("RenderReadyCharacterProfiles", profiles)
    after = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    assert before == after
    output = run / "snapshots-dev29"
    expected = {"document-character-appearance-states.json": states,
                "character-snapshots.json": snapshots, "render-ready-character-profiles.json": profiles}
    existed = output.exists()
    if existed:
        for name, value in expected.items():
            assert read(output / name) == value, "saved output differs; use a new versioned destination"
    else:
        output.mkdir()
        for name, value in expected.items():
            write(output / name, value)
    summary = {"snapshots": len(snapshots), "model_calls": 0,
               "active_fact_bindings": sum(len(s["active_fact_ids"]) for s in snapshots),
               "provisional_fact_bindings": sum(len(s["provisional_fact_ids"]) for s in snapshots),
               "excluded_fact_bindings": sum(len(s["excluded_facts"]) for s in snapshots),
               "source_hashes_unchanged": before, "deterministic": True,
               "legacy_schema_valid": True, "current_schema_valid": True,
               "snapshot_sha256": hashlib.sha256((output / "character-snapshots.json").read_bytes()).hexdigest()}
    if existed:
        assert read(output / "summary.json") == summary
    else:
        write(output / "summary.json", summary)
    print(json.dumps({k: v for k, v in summary.items() if k != "source_hashes_unchanged"}, indent=2))


if __name__ == "__main__":
    main()
