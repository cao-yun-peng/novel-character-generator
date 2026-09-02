import json
import tempfile
import unittest
from pathlib import Path

from novel_character_generator.appearance_scope import (
    APPEARANCE_SCOPE_POLICY_VERSION,
    DOCUMENT_CHARACTER_APPEARANCE_SCOPES_VERSION,
    build_document_character_appearance_scopes,
    parse_document_chapters,
    run_document_appearance_scope_assembly,
)
from novel_character_generator.errors import ContractValidationError
from novel_character_generator.fact_groups import (
    DOCUMENT_CHARACTER_FACT_GROUPS_VERSION,
    POST_LINK_FACT_GROUPING_POLICY_VERSION,
)
from novel_character_generator.text import sha256_text


def _fact(fact_id, character_id, quote, start, category):
    return {
        "canonical_fact_id": fact_id,
        "character_id": character_id,
        "fact_quote": quote,
        "category": category,
        "attribute": "属性",
        "value": quote,
        "document_fact_span": {"start": start, "end": start + len(quote)},
        "source_fact_hashes": ["a" * 64],
        "source_occurrences": [{}],
        "grouping_reason": "same_character_span_category_attribute_value",
        "scope_assignment_status": "unassigned",
    }


def _inputs():
    text = "第1章 开始\r\n　　第1章 开始 \r\n少年红衣。\r\n第2章 后来\r\n少年二十岁，有胎记。"
    character_id = "char-" + "1" * 20
    facts = [
        _fact("cfact-" + "1" * 20, character_id, "红衣", text.index("红衣"), "clothing"),
        _fact("cfact-" + "2" * 20, character_id, "二十岁", text.index("二十岁"), "age"),
        _fact("cfact-" + "3" * 20, character_id, "胎记", text.index("胎记"), "distinctive_mark"),
    ]
    groups = {
        "schema_version": DOCUMENT_CHARACTER_FACT_GROUPS_VERSION,
        "grouping_policy_version": POST_LINK_FACT_GROUPING_POLICY_VERSION,
        "source_document_version_id": "doc-v1",
        "document_hash": sha256_text(text),
        "coverage_status": "complete",
        "processed_source_end": len(text),
        "source_artifacts": {},
        "characters": [
            {
                "character_id": character_id,
                "identity_status": "linked",
                "canonical_label": "少年",
                "canonical_fact_ids": [fact["canonical_fact_id"] for fact in facts],
            }
        ],
        "fact_groups": facts,
        "unassigned_source_fact_hashes": [],
        "unassigned_source_occurrences": [],
        "summary": {"canonical_fact_groups": 3},
    }
    return text, groups


class AppearanceScopeTests(unittest.TestCase):
    def test_duplicate_adjacent_heading_is_one_boundary(self):
        text, _ = _inputs()
        chapters = parse_document_chapters(text)
        self.assertEqual([item["chapter_number"] for item in chapters], [1, 2])
        self.assertEqual(chapters[0]["document_span"]["start"], 0)
        self.assertEqual(chapters[-1]["document_span"]["end"], len(text))

    def test_assigns_every_fact_once_with_conservative_persistence(self):
        text, groups = _inputs()
        result = build_document_character_appearance_scopes(
            document_text=text,
            fact_groups=groups,
        )
        self.assertEqual(result["schema_version"], DOCUMENT_CHARACTER_APPEARANCE_SCOPES_VERSION)
        self.assertEqual(result["scope_policy_version"], APPEARANCE_SCOPE_POLICY_VERSION)
        self.assertEqual(result["summary"]["canonical_facts"], 3)
        self.assertEqual([item["order"] for item in result["fact_assignments"]], [0, 1, 2])
        self.assertEqual([item["chapter_number"] for item in result["fact_assignments"]], [1, 2, 2])
        self.assertEqual(
            [item["persistence"] for item in result["fact_assignments"]],
            ["scene", "persistent_until_changed", "stable"],
        )
        for item in result["fact_assignments"]:
            self.assertEqual((item["life"], item["form"], item["scene"]), ("unknown",) * 3)
            self.assertEqual(
                set(item),
                {"canonical_fact_id", "character_id", "chapter_number", "order", "life", "form", "scene", "persistence"},
            )

    def test_tampered_document_or_fact_span_fails_closed(self):
        text, groups = _inputs()
        with self.assertRaises(ContractValidationError):
            build_document_character_appearance_scopes(document_text=text + "x", fact_groups=groups)
        text, groups = _inputs()
        groups["fact_groups"][0]["document_fact_span"] = {"start": 0, "end": 2}
        with self.assertRaises(ContractValidationError):
            build_document_character_appearance_scopes(document_text=text, fact_groups=groups)

    def test_runner_writes_output(self):
        text, groups = _inputs()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "groups.json"
            output = root / "out" / "scopes.json"
            source.write_text(json.dumps(groups, ensure_ascii=False), encoding="utf-8")
            summary = run_document_appearance_scope_assembly(
                document_text=text,
                fact_groups_file=source,
                output_file=output,
            )
            self.assertEqual(summary["canonical_facts"], 3)
            self.assertTrue(output.exists())


if __name__ == "__main__":
    unittest.main()
