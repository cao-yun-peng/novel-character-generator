from __future__ import annotations

import json
from pathlib import Path

import pytest

from novel_character_generator.appearance_transition import (
    AppearanceTransitionChunk,
    WindowCharacter,
    build_appearance_transition_chunks,
    build_transition_request,
    deduplicate_grounded_transitions,
    ground_transition_events,
    materialize_appearance_states,
    parse_transition_model_output,
)
from novel_character_generator.appearance_transition_batch import (
    prepare_document_appearance_transitions,
    run_document_appearance_transitions,
)
from novel_character_generator.chunking import build_document_chunk_manifest
from novel_character_generator.errors import ContractValidationError
from novel_character_generator.text import SourceSpan, sha256_text


def _sources(
    text: str, *, chunk_size: int = 40, overlap_characters: int = 10
) -> tuple[dict[str, object], ...]:
    source_version = "source-test"
    manifest = build_document_chunk_manifest(
        text,
        source_document_version_id=source_version,
        chunk_size=chunk_size,
        overlap_characters=overlap_characters,
    ).to_dict()
    source_refs = [
        {
            "source_document_version_id": source_version,
            "chunk_id": chunk["chunk_id"],
            "local_mention_id": f"m{index}",
        }
        for index, chunk in enumerate(manifest["chunks"], start=1)
    ]
    fact_start = text.rindex("黑发")
    fact_end = fact_start + len("黑发")
    profiles = {
        "source_document_version_id": source_version,
        "document_hash": sha256_text(text),
        "characters": [
            {
                "character_id": "char-suyuntao",
                "canonical_label": "素云涛",
                "labels": [
                    {"label_quote": "素云涛"},
                    {"label_quote": "年轻人"},
                ],
                "member_character_refs": [
                    {"ref_type": "local", "local_character_ref": source_ref}
                    for source_ref in source_refs
                ],
                "appearance_facts": [
                    {
                        "document_fact_span": {"start": fact_start, "end": fact_end}
                    }
                ],
            }
        ],
    }
    nodes = {
        "source_document_version_id": source_version,
        "document_hash": sha256_text(text),
        "nodes": [
            {
                "ref_type": "local",
                "source_character_ref": source_ref,
                "label_quote": (
                    "年轻人"
                    if "年轻人"
                    in text[chunk["chunk_source_span"]["start"] : chunk["chunk_source_span"]["end"]]
                    else "素云涛"
                ),
                "chunk_id": chunk["chunk_id"],
                "chunk_source_span": chunk["chunk_source_span"],
                "context_bindings": [
                    {
                        "context_quote": text[
                            chunk["chunk_source_span"]["start"] : min(
                                chunk["chunk_source_span"]["start"] + 10,
                                chunk["chunk_source_span"]["end"],
                            )
                        ],
                        "document_span": {
                            "start": chunk["chunk_source_span"]["start"],
                            "end": min(
                                chunk["chunk_source_span"]["start"] + 10,
                                chunk["chunk_source_span"]["end"],
                            ),
                        },
                    }
                ],
                "appearance_fact_refs": [],
            }
            for source_ref, chunk in zip(source_refs, manifest["chunks"])
        ],
    }
    scopes = {
        "source_document_version_id": source_version,
        "coverage_status": "complete",
        "processed_source_end": len(text),
        "chapters": [
            {
                "chapter_number": 1,
                "title": "测试",
                "document_span": {"start": 0, "end": len(text)},
            }
        ],
        "fact_assignments": [
            {
                "canonical_fact_id": "cfact-1",
                "character_id": "char-suyuntao",
                "chapter_number": 1,
                "order": 1,
                "life": "unknown",
                "form": "unknown",
                "scene": "unknown",
                "persistence": "unknown",
            }
        ],
    }
    fact_groups = {
        "source_document_version_id": source_version,
        "document_hash": sha256_text(text),
        "fact_groups": [
            {
                "canonical_fact_id": "cfact-1",
                "character_id": "char-suyuntao",
                "fact_quote": "黑发",
                "category": "hair",
                "attribute": "头发颜色",
                "value": "黑色",
                "document_fact_span": {"start": fact_start, "end": fact_end},
            }
        ],
    }
    return profiles, nodes, scopes, fact_groups, manifest


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def test_windows_cover_full_text_and_model_payload_has_no_system_fields() -> None:
    text = "第一章 测试\n素云涛化为独狼。" + "甲" * 45 + "年轻人收回武魂。黑发"
    profiles, nodes, scopes, _, manifest = _sources(text)
    profiles["characters"].append(
        {
            "character_id": "char-tangsan",
            "canonical_label": "唐三",
            "labels": [{"label_quote": "唐三"}],
            "member_character_refs": [],
            "appearance_facts": [],
        }
    )
    source_version, source_policy, windows = build_appearance_transition_chunks(
        document_text=text,
        profiles=profiles,
        local_nodes=nodes,
        scopes=scopes,
        chunk_manifest=manifest,
    )

    assert source_version == "source-test"
    assert source_policy == "fixed-codepoint-window-v1"
    assert windows[0].document_span.start == 0
    assert windows[-1].document_span.end == len(text)
    assert all(
        current.document_span.end >= following.document_span.start
        for current, following in zip(windows, windows[1:])
    )
    assert all(window.characters for window in windows)
    assert all([character.name for character in window.characters] == ["素云涛"] for window in windows)
    payload = build_transition_request(windows[-1]).user_payload
    serialized = json.dumps(payload, ensure_ascii=False)
    for forbidden in ("character_id", "chunk_id", "document_span", "hash", "source-test"):
        assert forbidden not in serialized
    assert payload["characters"] == [{"name": "素云涛", "aliases": ["年轻人"]}]


def test_source_chunk_manifest_is_fail_closed() -> None:
    text = "第一章 测试\n素云涛化为独狼。" + "甲" * 45 + "黑发"
    profiles, nodes, scopes, _, manifest = _sources(text)
    manifest["chunks"][0]["chunk_hash"] = "0" * 64
    with pytest.raises(ContractValidationError, match="Chunk hash"):
        build_appearance_transition_chunks(
            document_text=text,
            profiles=profiles,
            local_nodes=nodes,
            scopes=scopes,
            chunk_manifest=manifest,
        )


def test_parser_rejects_unknown_character_and_redundant_state() -> None:
    valid = {
        "events": [
            {
                "character": "素云涛",
                "evidence": "素云涛化为独狼",
                "dimension": "form",
                "attribute": "form_state",
                "before": "",
                "after": "化为独狼",
            }
        ]
    }
    assert parse_transition_model_output(valid, allowed_characters=["素云涛"])[0]["after"] == "化为独狼"
    invalid_character = json.loads(json.dumps(valid, ensure_ascii=False))
    invalid_character["events"][0]["character"] = "陌生人"
    with pytest.raises(ContractValidationError, match="window roster"):
        parse_transition_model_output(invalid_character, allowed_characters=["素云涛"])
    invalid_state = json.loads(json.dumps(valid, ensure_ascii=False))
    invalid_state["events"][0]["before"] = "化为独狼"
    with pytest.raises(ContractValidationError, match="cannot be equal"):
        parse_transition_model_output(invalid_state, allowed_characters=["素云涛"])


def test_grounding_requires_one_verbatim_occurrence_and_deduplicates_overlap() -> None:
    text = "素云涛化为独狼，随后素云涛化为独狼。"
    window = AppearanceTransitionChunk(
        number=1,
        chunk_id="chunk-test",
        chunk_hash=sha256_text(text),
        document_span=SourceSpan(100, 100 + len(text)),
        text=text,
        characters=(WindowCharacter("char-1", "素云涛", ()),),
    )
    ambiguous = (
        {
            "character": "素云涛",
            "evidence": "素云涛化为独狼",
            "dimension": "form",
            "attribute": "form_state",
            "before": "",
            "after": "化为独狼",
        },
    )
    grounded, issues = ground_transition_events(window, ambiguous)
    assert grounded == ()
    assert issues[0]["reason"] == "evidence_not_unique"

    unique_event = dict(ambiguous[0])
    unique_event["evidence"] = "随后素云涛化为独狼"
    grounded, issues = ground_transition_events(window, (unique_event,))
    assert not issues
    assert grounded[0]["document_span"]["start"] == 108
    assert len(deduplicate_grounded_transitions([grounded[0], grounded[0]])) == 1


def test_grounding_rejects_external_form_and_unsupported_or_cross_paragraph_state() -> None:
    text = (
        "唐三控制着把自己的蓝银草收回体内。"
        "唐三永远离开了这个世界。\n"
        "眼前的是五、六岁的孩子。"
    )
    window = AppearanceTransitionChunk(
        number=1,
        chunk_id="chunk-test",
        chunk_hash=sha256_text(text),
        document_span=SourceSpan(0, len(text)),
        text=text,
        characters=(WindowCharacter("char-1", "唐三", ()),),
    )
    events = (
        {
            "character": "唐三",
            "evidence": "唐三控制着把自己的蓝银草收回体内",
            "dimension": "form",
            "attribute": "form_state",
            "before": "蓝银草",
            "after": "收回体内",
        },
        {
            "character": "唐三",
            "evidence": "唐三永远离开了这个世界",
            "dimension": "life",
            "attribute": "life_stage",
            "before": "离开了这个世界",
            "after": "五、六岁的孩子",
        },
        {
            "character": "唐三",
            "evidence": "唐三永远离开了这个世界。\n眼前的是五、六岁的孩子",
            "dimension": "life",
            "attribute": "life_stage",
            "before": "离开了这个世界",
            "after": "五、六岁的孩子",
        },
    )
    grounded, issues = ground_transition_events(window, events)
    assert grounded == ()
    assert [item["reason"] for item in issues] == [
        "form_without_body_change_evidence",
        "state_not_supported_by_evidence",
        "evidence_crosses_scene_boundary",
    ]


def test_grounding_normalizes_explicit_form_exit_without_inventing_restored_state() -> None:
    text = "素云涛全身青光收敛，收回了自己的武魂附体"
    window = AppearanceTransitionChunk(
        number=1,
        chunk_id="chunk-test",
        chunk_hash=sha256_text(text),
        document_span=SourceSpan(100, 100 + len(text)),
        text=text,
        characters=(WindowCharacter("char-1", "素云涛", ()),),
    )
    grounded, issues = ground_transition_events(
        window,
        (
            {
                "character": "素云涛",
                "evidence": text,
                "dimension": "form",
                "attribute": "form_state",
                "before": "武魂附体",
                "after": "武魂附体收回",
            },
        ),
    )
    assert not issues
    assert grounded[0]["before"] == "武魂附体"
    assert grounded[0]["after"] == ""
    assert grounded[0]["change"] == "exit"


def test_grounding_restores_omitted_punctuation_to_one_continuous_state_span() -> None:
    text = "素云涛低喝一声，独狼，附体。"
    window = AppearanceTransitionChunk(
        number=1,
        chunk_id="chunk-test",
        chunk_hash=sha256_text(text),
        document_span=SourceSpan(0, len(text)),
        text=text,
        characters=(WindowCharacter("char-1", "素云涛", ()),),
    )
    grounded, issues = ground_transition_events(
        window,
        (
            {
                "character": "素云涛",
                "evidence": text,
                "dimension": "form",
                "attribute": "form_state",
                "before": "",
                "after": "独狼附体",
            },
        ),
    )
    assert not issues
    assert grounded[0]["after"] == "独狼，附体"


def test_materialization_applies_only_grounded_prior_state() -> None:
    text = "第一章 测试\n素云涛化为独狼。稍后观察。黑发"
    _, _, scopes, fact_groups, _ = _sources(text)
    evidence = "素云涛化为独狼"
    start = text.index(evidence)
    transitions = [
        {
            "character_id": "char-suyuntao",
            "evidence": evidence,
            "document_span": {"start": start, "end": start + len(evidence)},
            "dimension": "form",
            "attribute": "form_state",
            "before": "",
            "after": "化为独狼",
            "change": "enter",
        }
    ]
    result = materialize_appearance_states(
        document_text=text,
        source_document_version_id="source-test",
        scopes=scopes,
        fact_groups=fact_groups,
        transitions=transitions,
        review=[],
        planned_chunks=1,
        model_calls=1,
    )
    assert result["fact_assignments"][0]["form"] == "化为独狼"
    assert result["fact_assignments"][0]["life"] == "unknown"


def test_materialization_expires_scene_at_paragraph_and_resets_form_on_life_change() -> None:
    text = (
        "第一章 测试\n"
        "素云涛换上战袍并化为独狼，灰色毛发。\n"
        "稍后仍有绿眼。\n"
        "后来素云涛转生为幼儿，黑发。"
    )
    fact_quotes = ("灰色毛发", "绿眼", "黑发")
    groups = []
    assignments = []
    for order, quote in enumerate(fact_quotes, start=1):
        start = text.index(quote)
        canonical_id = f"cfact-{order}"
        groups.append(
                {
                    "canonical_fact_id": canonical_id,
                    "character_id": "char-suyuntao",
                    "category": "other_visual",
                    "attribute": quote,
                    "value": quote,
                    "document_fact_span": {"start": start, "end": start + len(quote)},
                }
        )
        assignments.append(
            {
                "canonical_fact_id": canonical_id,
                "character_id": "char-suyuntao",
                "chapter_number": 1,
                "order": order,
                "life": "unknown",
                "form": "unknown",
                "scene": "unknown",
                "persistence": "unknown",
            }
        )
    scopes = {
        "chapters": [
            {"chapter_number": 1, "title": "测试", "document_span": {"start": 0, "end": len(text)}}
        ],
        "fact_assignments": assignments,
    }
    fact_groups = {
        "source_document_version_id": "source-test",
        "document_hash": sha256_text(text),
        "fact_groups": groups,
    }
    first_evidence = "素云涛换上战袍并化为独狼"
    first_start = text.index(first_evidence)
    life_evidence = "素云涛转生为幼儿"
    life_start = text.index(life_evidence)
    transitions = [
        {
            "character_id": "char-suyuntao",
            "evidence": first_evidence,
            "document_span": {"start": first_start, "end": first_start + len(first_evidence)},
            "dimension": "scene",
            "attribute": "scene_state",
            "before": "",
            "after": "战袍",
            "change": "enter",
        },
        {
            "character_id": "char-suyuntao",
            "evidence": first_evidence,
            "document_span": {"start": first_start, "end": first_start + len(first_evidence)},
            "dimension": "form",
            "attribute": "form_state",
            "before": "",
            "after": "化为独狼",
            "change": "enter",
        },
        {
            "character_id": "char-suyuntao",
            "evidence": life_evidence,
            "document_span": {"start": life_start, "end": life_start + len(life_evidence)},
            "dimension": "life",
            "attribute": "life_stage",
            "before": "",
            "after": "幼儿",
            "change": "enter",
        },
    ]
    result = materialize_appearance_states(
        document_text=text,
        source_document_version_id="source-test",
        scopes=scopes,
        fact_groups=fact_groups,
        transitions=transitions,
        review=[],
        planned_chunks=1,
        model_calls=1,
    )
    first, second, third = result["fact_assignments"]
    assert (first["form"], first["scene"]) == ("化为独狼", "战袍")
    assert (second["form"], second["scene"]) == ("化为独狼", "unknown")
    assert (third["life"], third["form"], third["scene"]) == (
        "幼儿",
        "unknown",
        "unknown",
    )


class _FakeTrace:
    def to_dict(self) -> dict[str, object]:
        return {"provider": "fake", "success": True}


class _FakeProvider:
    cache_identity = {"provider": "test-test_appearance_transition.py"}
    def __init__(self, traces: list[object] | None = None) -> None:
        self.requests: list[object] = []
        self.traces = traces

    def generate(self, request: object) -> dict[str, object]:
        self.requests.append(request)
        if self.traces is not None:
            self.traces.append(_FakeTrace())
        payload = request.user_payload
        evidence = "素云涛化为独狼"
        if evidence not in payload["text"]:
            return {"events": []}
        return {
            "events": [
                {
                    "character": "素云涛",
                    "evidence": evidence,
                    "dimension": "form",
                    "attribute": "form_state",
                    "before": "",
                    "after": "化为独狼",
                }
            ]
        }


def test_prepare_and_resumable_batch(tmp_path: Path) -> None:
    text = "第一章 测试\n素云涛化为独狼。" + "甲" * 30 + "黑发"
    profiles, nodes, scopes, fact_groups, manifest = _sources(
        text, chunk_size=35, overlap_characters=10
    )
    profiles_path = tmp_path / "profiles.json"
    nodes_path = tmp_path / "nodes.json"
    scopes_path = tmp_path / "scopes.json"
    groups_path = tmp_path / "groups.json"
    manifest_path = tmp_path / "manifest.json"
    for path, value in (
        (profiles_path, profiles),
        (nodes_path, nodes),
        (scopes_path, scopes),
        (groups_path, fact_groups),
        (manifest_path, manifest),
    ):
        _write_json(path, value)
    output_dir = tmp_path / "run"

    prepared = prepare_document_appearance_transitions(
        document_text=text,
        profiles_file=profiles_path,
        local_nodes_file=nodes_path,
        scopes_file=scopes_path,
        chunk_manifest_file=manifest_path,
        output_dir=output_dir,
    )
    assert prepared["planned_chunks"] > 1
    assert prepared["model_calls"] == 0

    traces: list[object] = []
    provider = _FakeProvider(traces)
    first = run_document_appearance_transitions(
        document_text=text,
        profiles_file=profiles_path,
        local_nodes_file=nodes_path,
        fact_groups_file=groups_path,
        scopes_file=scopes_path,
        chunk_manifest_file=manifest_path,
        output_dir=output_dir,
        provider=provider,
        traces=traces,
    )
    assert first["complete"] is True
    assert first["grounded_transitions"] == 1
    calls = len(provider.requests)
    assert calls == prepared["chunks_with_characters"]
    states = json.loads(
        (output_dir / "document-character-appearance-states.json").read_text(encoding="utf-8")
    )
    assert states["transitions"][0]["character_id"] == "char-suyuntao"
    assert len(json.loads((output_dir / "provider-traces.json").read_text(encoding="utf-8"))) == calls

    event_result_path = next(
        path
        for path in (output_dir / "chunks").glob("*.json")
        if json.loads(path.read_text(encoding="utf-8"))["model_output"]["events"]
    )
    stale = json.loads(event_result_path.read_text(encoding="utf-8"))
    stale["grounded_transitions"] = []
    _write_json(event_result_path, stale)

    second = run_document_appearance_transitions(
        document_text=text,
        profiles_file=profiles_path,
        local_nodes_file=nodes_path,
        fact_groups_file=groups_path,
        scopes_file=scopes_path,
        chunk_manifest_file=manifest_path,
        output_dir=output_dir,
        provider=provider,
        traces=traces,
    )
    assert second["new_provider_calls"] == 0
    assert second["resumed_chunks"] == prepared["planned_chunks"]
    assert len(provider.requests) == calls
    refreshed = json.loads(event_result_path.read_text(encoding="utf-8"))
    assert refreshed["grounded_transitions"]
    # A changed provider must be rejected before any missing chunk is regenerated.
    earlier = [p for p in (output_dir / "chunks").glob("*.json") if p != event_result_path]
    if earlier:
        earlier[0].unlink()
    provider.cache_identity = {"provider": "changed-model"}
    with pytest.raises(ContractValidationError, match="fingerprint"):
        run_document_appearance_transitions(
            document_text=text, profiles_file=profiles_path, local_nodes_file=nodes_path,
            fact_groups_file=groups_path, scopes_file=scopes_path, chunk_manifest_file=manifest_path,
            output_dir=output_dir, provider=provider, traces=traces,
        )
    assert len(provider.requests) == calls

    assert len(json.loads((output_dir / "provider-traces.json").read_text(encoding="utf-8"))) == calls
