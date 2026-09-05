import copy
import json

import pytest

from novel_character_generator.character_snapshot import (
    build_character_snapshot, snapshot_to_render_profile, run_character_snapshot,
)
from novel_character_generator.fact_applicability import APPLICABILITY_EVENTS_VERSION
from novel_character_generator.appearance_scope import build_document_character_appearance_scopes
from novel_character_generator.appearance_transition import materialize_appearance_states
from novel_character_generator.errors import ContractValidationError
from novel_character_generator.render_profile_compiler import build_render_ready_character_profiles
from novel_character_generator.text import sha256_text
from test_render_profile_compiler import _fixture, _fact, _span, _request, SOURCE_VERSION, CHARACTER_A, CHARACTER_B


TEXT = ("第一章\n甲穿红衣，内衬白衫，佩玉佩，微笑。\n仍穿原衣走到门外。\n"
        "第二章\n他继续走向城门，衣着如前。\n他脱下红衣。\n换上蓝衣。\n"
        "他离场片刻又回来。\n十年之后。\n他的笑容消失了。\n")
RED, SHIRT, PENDANT, SMILE, BLUE = ["cfact-" + str(i) * 20 for i in range(1, 6)]


def sources(text=TEXT, transitions=()):
    _, groups, _, labels = _fixture()
    specs = [(RED, "红衣", "clothing"), (SHIRT, "白衫", "clothing"),
             (PENDANT, "玉佩", "accessory"), (SMILE, "微笑", "appearance_state"),
             (BLUE, "蓝衣", "clothing")]
    facts = [_fact(text, fact_id=fid, character_id=CHARACTER_A, quote=q,
                   category=category, attribute="衣着" if category == "clothing" else category, value=q)
             for fid, q, category in specs]
    for fact in facts:
        fact["source_occurrences"][0]["source_occurrence"]["source_character_ref"].update(
            local_mention_id="m1", mention_type="exact", packet_hash="a" * 64)
    groups.update(document_hash=sha256_text(text), processed_source_end=len(text), fact_groups=facts)
    groups["summary"]["canonical_fact_groups"] = len(facts)
    groups["characters"][0]["canonical_fact_ids"] = [f["canonical_fact_id"] for f in facts]
    groups["characters"][1]["canonical_fact_ids"] = []
    labels["document_hash"] = sha256_text(text)
    scopes = build_document_character_appearance_scopes(document_text=text, fact_groups=groups)
    states = materialize_appearance_states(document_text=text, source_document_version_id=SOURCE_VERSION,
        scopes=scopes, fact_groups=groups, transitions=list(transitions), review=[], planned_chunks=1, model_calls=0)
    return dict(document_text=text, fact_groups=groups, appearance_states=states, label_projection=labels)


def event(kind, quote, ids=(RED,), text=TEXT):
    return dict(character_id=CHARACTER_A, kind=kind, fact_ids=list(ids), evidence=quote,
                document_span=_span(text, quote))


def artifact(*events, text=TEXT):
    return dict(schema_version=APPLICABILITY_EVENTS_VERSION, source_document_version_id=SOURCE_VERSION,
                document_hash=sha256_text(text), events=list(events))


def query(position, *events, source=None, **kwargs):
    source = source or sources()
    return build_character_snapshot(**source, run_id="run-test", character_id=CHARACTER_A,
        document_position=position, explain=True,
        applicability_events=artifact(*events, text=source["document_text"]), **kwargs)


def detail(snapshot, fid):
    return next(x for x in snapshot["applicability"] + snapshot["excluded_facts"] if x["canonical_fact_id"] == fid)


@pytest.mark.parametrize("quote", ["仍穿原衣", "第二章", "城门", "离场片刻", "十年之后"])
def test_clothing_survives_layout_location_absence_and_time_as_provisional(quote):
    snapshot = query(TEXT.index(quote))
    assert detail(snapshot, RED)["status"] == "provisional"
    assert detail(snapshot, RED)["reason"] == "uncertain_continuity"
    assert detail(snapshot, SMILE)["reason"] == "expired_momentary"


def test_continuity_and_removal_are_half_open_and_do_not_remove_other_layers():
    continuous = event("continuity", "他继续走向城门，衣着如前。", (RED, SHIRT))
    removal = event("remove", "他脱下红衣。")
    pos = TEXT.index("城门")
    during = query(pos, continuous, removal)
    assert detail(during, RED)["status"] == "active"
    assert detail(during, RED)["valid_interval"] == continuous["document_span"]
    assert detail(query(continuous["document_span"]["end"], continuous), RED)["status"] == "provisional"
    end = removal["document_span"]["end"]
    assert detail(query(end - 1, removal), RED)["status"] == "provisional"
    after = query(end, removal)
    assert detail(after, RED)["reason"] == "removed"
    assert detail(after, SHIRT)["status"] == detail(after, PENDANT)["status"] == "provisional"
    assert detail(after, BLUE)["reason"] == "future_observation"
    assert detail(after, RED)["basis_event_ids"]
    assert detail(after, RED)["provenance"]["source_occurrences"]


def test_new_clothing_observation_does_not_implicitly_replace_or_remove_old():
    pos = TEXT.index("蓝衣")
    snapshot = query(pos)
    assert detail(snapshot, BLUE)["status"] == "active"
    assert detail(snapshot, RED)["status"] == detail(snapshot, SHIRT)["status"] == "provisional"
    replacement = event("replace", "换上蓝衣。")
    after = query(replacement["document_span"]["end"], replacement)
    assert detail(after, RED)["reason"] == "replaced"
    assert detail(after, SHIRT)["status"] == "provisional"


def test_same_position_events_are_order_independent_and_deduplicated():
    # Continuity starts where the removal ends. Closure wins without inventing order.
    removal = event("remove", "他脱下红衣。")
    continuity = event("continuity", "\n换上蓝衣。")
    pos = removal["document_span"]["end"]
    first = query(pos, removal, continuity, removal)
    second = query(pos, continuity, removal)
    assert first == second
    assert detail(first, RED)["reason"] == "removed"


def test_gap_invalidates_continuity_certainty_without_claiming_removal():
    gap = event("uncertain_gap", "十年之后。", (RED, SHIRT))
    snapshot = query(gap["document_span"]["end"], gap)
    assert detail(snapshot, RED)["reason"] == "uncertain_continuity"
    assert detail(snapshot, RED)["basis_event_ids"]
    assert detail(snapshot, RED)["valid_interval"]["end"] is None


@pytest.mark.parametrize("removed", [False, True])
def test_form_exit_restores_only_unremoved_base_clothing(removed):
    text = TEXT + "进入狼形。\n脱下白衫。\n退出狼形。\n此后。"
    enter = dict(character_id=CHARACTER_A, evidence="进入狼形", document_span=_span(text, "进入狼形"),
                 dimension="form", attribute="form_state", before="", after="狼形", change="enter")
    leave = dict(character_id=CHARACTER_A, evidence="退出狼形", document_span=_span(text, "退出狼形"),
                 dimension="form", attribute="form_state", before="狼形", after="", change="exit")
    source = sources(text, (enter, leave))
    events = [event("remove", "脱下白衫。", (SHIRT,), text)] if removed else []
    during = query(text.index("脱下白衫"), *events, source=source)
    assert detail(during, SHIRT)["reason"] == "different_form"
    after = query(text.index("此后"), *events, source=source)
    assert detail(after, SHIRT)["reason"] == ("removed" if removed else "restored_base_clothing_uncertain")
    assert detail(after, RED)["status"] == "provisional"


def test_life_boundary_prevents_restoration_even_if_life_label_returns():
    text, groups, states, labels = _fixture()
    snapshot = build_character_snapshot(document_text=text, fact_groups=groups, appearance_states=states,
        label_projection=labels, run_id="r", character_id=CHARACTER_A,
        document_position=text.index("身形幼小"), explain=True)
    assert detail(snapshot, RED)["reason"] == "different_life"


@pytest.mark.parametrize("mutation", ["document", "span", "owner", "future", "empty"])
def test_event_grounding_and_ownership_fail_closed(mutation):
    data = artifact(event("remove", "他脱下红衣。"))
    if mutation == "document": data["document_hash"] = "0" * 64
    elif mutation == "span": data["events"][0]["document_span"]["start"] += 1
    elif mutation == "owner": data["events"][0]["character_id"] = CHARACTER_B
    elif mutation == "future": data["events"][0]["fact_ids"] = [BLUE]
    else: data["events"][0]["fact_ids"] = []
    with pytest.raises(ContractValidationError):
        build_character_snapshot(**sources(), run_id="r", character_id=CHARACTER_A,
                                 document_position=0, applicability_events=data)


def test_snapshot_id_binds_run_artifacts_query_and_explain_is_only_expansion():
    source = sources()
    before = copy.deepcopy(source)
    args = dict(**source, run_id="one", character_id=CHARACTER_A, document_position=TEXT.index("城门"))
    small = build_character_snapshot(**args)
    full = build_character_snapshot(**args, explain=True)
    assert small["snapshot_id"] == full["snapshot_id"]
    assert "excluded_facts" not in small
    assert source == before
    for change in ({"run_id": "two"}, {"document_position": 1},
                   {"applicability_events": artifact(event("remove", "他脱下红衣。"))}):
        assert build_character_snapshot(**{**args, **change})["snapshot_id"] != small["snapshot_id"]
    request = _request(CHARACTER_A, position=args["document_position"], life=None, form=None, scene=None)
    legacy = build_render_ready_character_profiles(**source, requests=[request])["profiles"][0]
    assert snapshot_to_render_profile(small) == legacy


@pytest.mark.parametrize("position", [-1, len(TEXT), True])
def test_snapshot_rejects_invalid_positions(position):
    with pytest.raises(ContractValidationError): query(position)


def test_missing_position_and_incompatible_selector_do_not_mix_traits():
    for snapshot in (query(None), query(0, form_state="不存在")):
        assert snapshot["active_traits"] == snapshot["provisional_traits"] == []
        assert snapshot["selected_state_segment_id"] is None


def test_snapshot_cli_and_source_overwrite_guard(tmp_path):
    from novel_character_generator.__main__ import main
    source = sources()
    paths = {}
    for name, value in source.items():
        path = tmp_path / (name + ".json")
        path.write_text(value if isinstance(value, str) else json.dumps(value, ensure_ascii=False), encoding="utf-8", newline="")
        paths[name] = path
    output = tmp_path / "snapshot.json"
    command = ["build-character-snapshot", "--input-file", str(paths["document_text"]),
        "--fact-groups-file", str(paths["fact_groups"]), "--appearance-states-file", str(paths["appearance_states"]),
        "--label-projection-file", str(paths["label_projection"]), "--output-file", str(output),
        "--run-id", "run-test", "--character-id", CHARACTER_A, "--document-position", "10", "--explain"]
    assert main(command) == 0
    assert json.loads(output.read_text("utf-8"))["schema_version"] == "character-snapshot-v1"
    with pytest.raises(ContractValidationError, match="overwrite"):
        run_character_snapshot(document_text=TEXT, fact_groups_file=paths["fact_groups"],
            appearance_states_file=paths["appearance_states"], label_projection_file=paths["label_projection"],
            output_file=paths["fact_groups"], run_id="r", character_id=CHARACTER_A, document_position=0)


def test_snapshot_and_event_machine_schemas():
    from pathlib import Path
    from jsonschema import Draft202012Validator
    schema = json.loads((Path(__file__).parents[1] / "docs/contracts/simplified-character-evidence-v3-model-schemas.json").read_text("utf-8"))
    Draft202012Validator.check_schema(schema)
    for name, value in (
        ("ApplicabilityEvents", artifact(event("remove", "他脱下红衣。"))),
        ("CharacterSnapshot", query(TEXT.index("城门"), event("continuity", "他继续走向城门，衣着如前。"))),
        ("CharacterSnapshot", query(None)),
    ):
        Draft202012Validator({"$ref": "#/$defs/" + name, "$defs": schema["$defs"]}).validate(value)


def test_form_interval_does_not_claim_base_clothing_during_transformation():
    text = TEXT + "进入狼形。\n退出狼形。\n此后。"
    enter = dict(character_id=CHARACTER_A, evidence="进入狼形", document_span=_span(text, "进入狼形"),
                 dimension="form", attribute="form_state", before="", after="狼形", change="enter")
    leave = dict(character_id=CHARACTER_A, evidence="退出狼形", document_span=_span(text, "退出狼形"),
                 dimension="form", attribute="form_state", before="狼形", after="", change="exit")
    source = sources(text, (enter, leave))
    before = query(text.index("十年之后"), source=source)
    assert detail(before, RED)["valid_interval"]["end"] == text.index("狼形")
    after = query(text.index("此后"), source=source)
    assert detail(after, RED)["valid_interval"]["start"] >= leave["document_span"]["end"]


def test_existing_grounded_appearance_exit_closes_only_unique_matching_fact():
    transition = dict(character_id=CHARACTER_A, evidence="他脱下红衣", document_span=_span(TEXT, "他脱下红衣"),
                      dimension="appearance", attribute="衣着", before="红衣", after="", change="exit")
    source = sources(transitions=(transition,))
    end = transition["document_span"]["end"]
    assert detail(query(end - 1, source=source), RED)["status"] == "provisional"
    snapshot = query(end, source=source)
    assert detail(snapshot, RED)["reason"] == "removed"
    assert detail(snapshot, SHIRT)["status"] == "provisional"
    assert detail(snapshot, RED)["basis_event_ids"][0].startswith("transition-")
