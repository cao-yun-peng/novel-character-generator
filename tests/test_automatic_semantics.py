import copy
import json

import pytest

from novel_character_generator.automatic_semantics import (
    _descriptor, build_semantic_tasks, ground_event_output, ground_relation_output,
    run_automatic_semantics, semantic_request, validate_automatic_semantics,
)
from novel_character_generator.character_snapshot import build_character_snapshot, snapshot_to_render_profile
from novel_character_generator.chunking import build_document_chunk_manifest
from novel_character_generator.errors import ContractValidationError, ProviderError
from test_character_snapshot import sources, TEXT, RED, BLUE, SHIRT, SMILE, CHARACTER_A


def inputs(text=TEXT):
    source = sources(text)
    manifest = build_document_chunk_manifest(text,
        source_document_version_id=source["fact_groups"]["source_document_version_id"],
        chunk_size=len(text), overlap_characters=0).to_dict()
    return {**source, "chunk_manifest": manifest}


class Provider:
    cache_identity = {"provider": "scripted-semantic-regression", "model": "v1"}

    def __init__(self, events=(), incompatible=False):
        self.events, self.incompatible, self.calls = list(events), incompatible, 0

    def generate(self, request):
        self.calls += 1
        if "events" in request.response_schema["properties"]:
            return {"events": self.events}
        if self.incompatible and {request.user_payload[s]["fact"]["fact_quote"] for s in ("left", "right")} == {"红衣", "蓝衣"}:
            return {"relation": "incompatible", "evidence_quotes": [request.user_payload[s]["context"][0] for s in ("left", "right")]}
        return {"relation": "uncertain", "evidence_quotes": []}


def test_duplicate_relation_quotes_round_trip_to_snapshot(tmp_path):
    class DuplicateProvider(Provider):
        def generate(self, request):
            result = super().generate(request)
            if "evidence_quotes" in result:
                result["evidence_quotes"] *= 2
            return result

    source = inputs()
    output = tmp_path / "duplicates"
    run_automatic_semantics(**source, output_dir=output, provider=DuplicateProvider(incompatible=True))
    artifact = json.loads((output / "automatic-semantics.json").read_text("utf-8"))
    relation = next(r for r in artifact["relations"] if r["relation"] == "incompatible")
    assert len(relation["evidence"]) == 2
    snapshot(source, artifact, len(TEXT) - 1)


def model_event(source, kind, quote, ids=()):
    facts = {f["canonical_fact_id"]: f for f in source["fact_groups"]["fact_groups"]}
    return {"character": "唐三", "kind": kind, "evidence": quote,
            "facts": [_descriptor(facts[fid]) for fid in ids]}


def snapshot(source, artifact, position, **kwargs):
    return build_character_snapshot(**{k: v for k, v in source.items() if k != "chunk_manifest"},
        run_id="test-run", character_id=CHARACTER_A, document_position=position,
        automatic_semantics=artifact, explain=True, **kwargs)


def test_automatic_removal_and_scene_flow_to_snapshot_and_resume_replay(tmp_path):
    source = inputs()
    events = [model_event(source, "scene_boundary", "他继续走向城门，衣着如前。"),
              model_event(source, "remove", "他脱下红衣。", [RED]),
              model_event(source, "wear", "换上蓝衣。", [BLUE])]
    provider = Provider(events)
    output = tmp_path / "run"
    result = run_automatic_semantics(**source, output_dir=output, provider=provider)
    assert result["complete"] and result["events"] == 3
    artifact = json.loads((output / "automatic-semantics.json").read_text("utf-8"))
    before = snapshot(source, artifact, TEXT.index("他脱下"))
    assert RED in before["provisional_fact_ids"]
    after = snapshot(source, artifact, TEXT.index("换上蓝衣"))
    assert RED not in after["provisional_fact_ids"]
    assert SHIRT in after["provisional_fact_ids"]
    assert after["narrative_scene"]["status"] == "grounded_boundary"
    assert after["unresolved_conflicts"] == []
    calls = provider.calls
    resumed = run_automatic_semantics(**source, output_dir=output, provider=provider)
    assert resumed["new_provider_calls"] == 0 and provider.calls == calls
    replay = run_automatic_semantics(**source, output_dir=tmp_path / "replay", replay_dir=output)
    assert replay["new_provider_calls"] == 0
    assert json.loads((tmp_path / "replay/automatic-semantics.json").read_text("utf-8")) == artifact


@pytest.mark.parametrize("closure", [False, True])
def test_incompatibility_generates_conflict_only_for_two_active_facts(tmp_path, closure):
    text = TEXT + "红衣与蓝衣在此段同时保持原样。\n"
    source = inputs(text)
    events = [model_event(source, "continuity", "红衣与蓝衣在此段同时保持原样。", [RED, BLUE])]
    if closure:
        events.append(model_event(source, "replace", "换上蓝衣。", [RED]))
    run_automatic_semantics(**source, output_dir=tmp_path / "run", provider=Provider(events, True))
    artifact = json.loads((tmp_path / "run/automatic-semantics.json").read_text("utf-8"))
    provisional = snapshot(source, artifact, text.index("十年之后"))
    assert provisional["unresolved_conflicts"] == []
    at = snapshot(source, artifact, text.index("红衣与蓝衣"))
    assert bool(at["unresolved_conflicts"]) is not closure
    if not closure:
        assert at["unresolved_conflicts"][0]["relation"] == "true_conflict"
        assert at["unresolved_conflicts"][0]["applicability_status"] == "active_overlap"
        assert snapshot_to_render_profile(at)["unresolved_conflicts"] == at["unresolved_conflicts"]
        assert any(w["code"] == "provisional_incompatible_relation" for w in provisional["compile_warnings"])


@pytest.mark.parametrize("failure", ["evidence", "character", "future", "category", "empty"])
def test_event_grounding_rejects_unsafe_bindings(failure):
    source = inputs()
    tasks = build_semantic_tasks(**{k: source[k] for k in ("document_text", "fact_groups", "label_projection", "chunk_manifest")})
    raw = model_event(source, "remove", "他脱下红衣。", [RED])
    if failure == "evidence": raw["evidence"] = "他脱掉红衣"
    elif failure == "character": raw["character"] = "unknown"
    elif failure == "future": raw["facts"] = [model_event(source, "wear", "", [BLUE])["facts"][0]]
    elif failure == "category": raw["facts"] = [model_event(source, "wear", "", [SMILE])["facts"][0]]
    else: raw["facts"] = []
    accepted, rejected = ground_event_output(tasks[0], {"events": [raw]}, document_text=TEXT,
        facts={f["canonical_fact_id"]: f for f in source["fact_groups"]["fact_groups"]})
    assert accepted == [] and rejected


def test_repeat_quote_not_first_match_and_output_metadata_rejected():
    source = inputs(TEXT + "他脱下红衣。")
    task = build_semantic_tasks(**{k: source[k] for k in ("document_text", "fact_groups", "label_projection", "chunk_manifest")})[0]
    raw = model_event(source, "remove", "他脱下红衣。", [RED])
    facts = {f["canonical_fact_id"]: f for f in source["fact_groups"]["fact_groups"]}
    accepted, reviews = ground_event_output(task, {"events": [raw]}, document_text=source["document_text"], facts=facts)
    assert not accepted and "ambiguous" in reviews[0]["message"]
    with pytest.raises(ContractValidationError):
        ground_event_output(task, {"events": [], "span": {}}, document_text=source["document_text"], facts=facts)


def test_request_contains_no_internal_metadata():
    source = inputs()
    tasks = build_semantic_tasks(**{k: source[k] for k in ("document_text", "fact_groups", "label_projection", "chunk_manifest")})
    forbidden = {"character_id", "fact_ids", "canonical_fact_id", "span", "chunk_id", "hash", "task_id"}
    def visit(value):
        if isinstance(value, dict):
            assert not forbidden.intersection(value)
            for child in value.values(): visit(child)
        elif isinstance(value, list):
            for child in value: visit(child)
    for task in tasks:
        visit(semantic_request(task).user_payload)


@pytest.mark.parametrize("change", ["model", "missing_fingerprint", "budget"])
def test_preflight_fails_before_any_new_call(tmp_path, change):
    source = inputs()
    provider = Provider()
    out = tmp_path / "run"
    if change != "budget":
        run_automatic_semantics(**source, output_dir=out, provider=provider)
        paths = list((out / "tasks").glob("*.json"))
        paths[0].unlink()
        if change == "model": provider.cache_identity = {"model": "changed"}
        else:
            data = json.loads(paths[-1].read_text("utf-8"));data.pop("request_fingerprint")
            paths[-1].write_text(json.dumps(data), encoding="utf-8")
    calls = provider.calls
    with pytest.raises(ContractValidationError):
        run_automatic_semantics(**source, output_dir=out, provider=provider, max_new_calls=0 if change == "budget" else 100)
    assert provider.calls == calls


def test_incomplete_artifact_and_tampered_provenance_are_rejected(tmp_path):
    source = inputs()
    run_automatic_semantics(**source, output_dir=tmp_path / "r", provider=Provider(incompatible=True))
    original = json.loads((tmp_path / "r/automatic-semantics.json").read_text("utf-8"))
    for mode in ("incomplete", "hash", "span"):
        artifact = copy.deepcopy(original)
        if mode == "incomplete": artifact["complete"] = False
        elif mode == "hash": artifact["fact_groups_hash"] = "a" * 64
        else:
            relation = next(r for r in artifact["relations"] if r["relation"] == "incompatible")
            relation["evidence"][0]["document_span"]["start"] += 1
        with pytest.raises(ContractValidationError): snapshot(source, artifact, 0)


def test_incompatibility_requires_evidence_covering_both_sides():
    source = inputs()
    facts = {f["canonical_fact_id"]: f for f in source["fact_groups"]["fact_groups"]}
    task = {"character_id": CHARACTER_A, "fact_ids": [RED, BLUE]}
    with pytest.raises(ContractValidationError, match="both"):
        ground_relation_output(task, {"relation": "incompatible", "evidence_quotes": ["红衣"]},
                               document_text=TEXT, facts=facts)


def test_prepare_does_not_need_provider(tmp_path):
    result = run_automatic_semantics(**inputs(), output_dir=tmp_path / "p", prepare_only=True)
    assert result["planned_tasks"] > 1 and result["new_provider_calls"] == 0


def test_machine_schema_for_model_artifact_and_true_conflict(tmp_path):
    from pathlib import Path
    from jsonschema import Draft202012Validator
    schema = json.loads((Path(__file__).parents[1] / "docs/contracts/simplified-character-evidence-v3-model-schemas.json").read_text("utf-8"))
    Draft202012Validator.check_schema(schema)
    text = TEXT + "红衣与蓝衣在此段同时保持原样。\n"
    source = inputs(text)
    provider = Provider([model_event(source, "continuity", "红衣与蓝衣在此段同时保持原样。", [RED, BLUE])], True)
    run_automatic_semantics(**source, output_dir=tmp_path / "r", provider=provider)
    artifact = json.loads((tmp_path / "r/automatic-semantics.json").read_text("utf-8"))
    at = snapshot(source, artifact, text.index("红衣与蓝衣"))
    for name, value in [("AutomaticSemantics", artifact), ("CharacterSnapshot", at),
                        ("AutomaticEventModelOutput", {"events": provider.events}),
                        ("AutomaticRelationModelOutput", {"relation": "uncertain", "evidence_quotes": []})]:
        Draft202012Validator({"$ref": "#/$defs/" + name, "$defs": schema["$defs"]}).validate(value)


def test_provider_failure_prevents_query_and_missing_replay_never_calls(tmp_path):
    source = inputs()
    class Failing:
        cache_identity = {"provider": "fail"}
        def generate(self, request):
            raise ProviderError("offline failure")
    result = run_automatic_semantics(**source, output_dir=tmp_path / "r", provider=Failing())
    assert not result["complete"]
    artifact = json.loads((tmp_path / "r/automatic-semantics.json").read_text("utf-8"))
    with pytest.raises(ContractValidationError): snapshot(source, artifact, 0)
    with pytest.raises(ContractValidationError, match="missing"):
        run_automatic_semantics(**source, output_dir=tmp_path / "replay", replay_dir=tmp_path / "r")
    assert not (tmp_path / "replay").exists()


def test_scene_boundary_alone_never_removes_clothing(tmp_path):
    source = inputs()
    provider = Provider([model_event(source, "scene_boundary", "他继续走向城门，衣着如前。")])
    run_automatic_semantics(**source, output_dir=tmp_path / "r", provider=provider)
    artifact = json.loads((tmp_path / "r/automatic-semantics.json").read_text("utf-8"))
    at = snapshot(source, artifact, TEXT.index("换上蓝衣"))
    assert RED in at["provisional_fact_ids"] and SHIRT in at["provisional_fact_ids"]


@pytest.mark.parametrize("kind,quote,ids", [
    ("uncertain_gap", "十年之后。", [RED]),
    ("momentary_end", "他的笑容消失了。", [SMILE]),
    ("continuity", "仍穿原衣走到门外。", [RED, SHIRT]),
])
def test_other_automatic_events_bind_and_are_consumed(tmp_path, kind, quote, ids):
    source = inputs()
    run_automatic_semantics(**source, output_dir=tmp_path / "r",
                            provider=Provider([model_event(source, kind, quote, ids)]))
    artifact = json.loads((tmp_path / "r/automatic-semantics.json").read_text("utf-8"))
    at = snapshot(source, artifact, TEXT.index(quote) + (0 if kind == "continuity" else len(quote)))
    assert at["semantic_events"][0]["kind"] == kind
    if kind == "continuity": assert set(ids).issubset(at["active_fact_ids"])
    elif kind == "uncertain_gap": assert RED in at["provisional_fact_ids"]
    else: assert SMILE not in at["active_fact_ids"] + at["provisional_fact_ids"]
