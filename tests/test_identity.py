import json
import tempfile
import unittest
from hashlib import sha256
from pathlib import Path
from unittest import mock

from novel_character_generator.errors import ContractValidationError
from novel_character_generator.identity import (
    DocumentLocalCharacterNodes,
    GroundedIdentityDecision,
    GroundedIdentityEvidence,
    IdentityAppearanceFactRef,
    IdentityContextBinding,
    IdentityCurrentModelInput,
    IdentityCandidateModelInput,
    IdentityEnvelope,
    IdentityModelInput,
    IdentityModelOutput,
    IdentityOrchestrator,
    LocalCharacterNode,
    build_document_character_registry,
    build_identity_preparation,
    ground_identity_model_output,
)
from novel_character_generator.text import SourceSpan, sha256_text
from novel_character_generator.identity_batch import run_document_identity


def _canonical_hash(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(payload.encode("utf-8")).hexdigest()


def _node_key(ref_type: str, source_ref: dict[str, object]) -> str:
    return _canonical_hash({"ref_type": ref_type, "source_character_ref": source_ref})


def _node(
    *,
    index: int,
    label: str,
    text: str,
    context_span: SourceSpan,
    facts: tuple[IdentityAppearanceFactRef, ...] = (),
    label_type: str = "exact",
) -> LocalCharacterNode:
    ref_type = "local" if label_type == "exact" else "promoted"
    if ref_type == "local":
        source_ref: dict[str, object] = {
            "source_document_version_id": "doc-v1",
            "chunk_id": f"chunk-{index}",
            "local_mention_id": f"m{index}",
            "mention_type": "exact",
            "packet_hash": f"{index:064x}",
        }
    else:
        source_ref = {
            "source_document_version_id": "doc-v1",
            "chunk_id": f"chunk-{index}",
            "source_local_mention_id": f"m{index}",
            "source_mention_type": "describe",
            "promotion_index": 1,
            "character_origin": "remaining_describe",
            "packet_hash": f"{index:064x}",
            "promotion_hash": f"{index + 100:064x}",
        }
    return LocalCharacterNode(
        node_key=_node_key(ref_type, source_ref),
        ref_type=ref_type,
        source_character_ref=source_ref,
        character_origin="exact" if label_type == "exact" else "remaining_describe",
        label_quote=label,
        label_type=label_type,
        chunk_id=f"chunk-{index}",
        chunk_source_span=context_span,
        context_bindings=(IdentityContextBinding(context_span.quote(text), context_span, "node"),),
        appearance_fact_refs=facts,
        order_position=context_span.start,
    )


def _fact(
    *,
    fact_hash: str,
    quote: str,
    span: SourceSpan,
    value: str,
    attribute: str = "眼睛",
) -> IdentityAppearanceFactRef:
    return IdentityAppearanceFactRef(
        fact_hash=fact_hash,
        fact_quote=quote,
        category="face",
        attribute=attribute,
        value=value,
        document_fact_span=span,
    )


def _document_nodes(text: str, *nodes: LocalCharacterNode) -> DocumentLocalCharacterNodes:
    return DocumentLocalCharacterNodes("doc-v1", sha256_text(text), tuple(nodes))


class _Provider:
    def __init__(self, output: dict[str, object]) -> None:
        self.output = output
        self.requests = []

    def generate(self, request):
        self.requests.append(request)
        return self.output


class _FailIfCalledProvider:
    def generate(self, request):
        raise AssertionError("resumed identity task must not call the Provider")


class IdentityModelBoundaryTests(unittest.TestCase):
    def test_model_output_rejects_code_only_fields_and_invalid_conditions(self) -> None:
        with self.assertRaises(ContractValidationError):
            IdentityModelOutput.parse(
                {
                    "identity_relation": "same_character",
                    "label_relation": "alias",
                    "identity_evidence_quotes": ["她就是熏儿"],
                    "current_node_key": "hidden",
                }
            )
        with self.assertRaises(ContractValidationError):
            IdentityModelOutput.parse(
                {
                    "identity_relation": "uncertain",
                    "label_relation": None,
                    "identity_evidence_quotes": ["不允许"],
                }
            )

    def test_orchestrator_sends_only_minimal_model_payload(self) -> None:
        text = "萧熏儿被称作熏儿。"
        first = _node(index=1, label="萧熏儿", text=text, context_span=SourceSpan(0, 3))
        second = _node(index=2, label="熏儿", text=text, context_span=SourceSpan(6, 8))
        preparation = build_identity_preparation(
            local_nodes=_document_nodes(text, first, second),
            document_text=text,
            max_candidates_per_node=1,
        )
        provider = _Provider(
            {
                "identity_relation": "same_character",
                "label_relation": "alias",
                "identity_evidence_quotes": ["熏儿"],
            }
        )
        IdentityOrchestrator(provider).run(preparation.envelopes[0], document_text=text)
        request = provider.requests[0]
        serialized = json.dumps(request.user_payload, ensure_ascii=False)
        self.assertEqual(
            set(request.user_payload),
            {"current_character", "candidate_character", "bridge_context_quotes"},
        )
        for forbidden in ("node_key", "character_id", "span", "hash", "ref", "cache"):
            self.assertNotIn(forbidden, serialized)


class IdentityGroundingTests(unittest.TestCase):
    def _envelope(self, text: str, bindings: tuple[IdentityContextBinding, ...]) -> IdentityEnvelope:
        model_input = IdentityModelInput(
            current_character=IdentityCurrentModelInput("熏儿", "exact", tuple(b.context_quote for b in bindings), ()),
            candidate_character=IdentityCandidateModelInput(("萧熏儿",), (), ()),
            bridge_context_quotes=(),
        )
        hash_input = {
            "schema_version": "m3-identity-envelope-v1",
            "current_node_key": "current",
            "candidate_node_key": "candidate",
            "candidate_reasons": ["label_contains"],
            "context_policy_version": "identity-evidence-window-v1",
            "model_input": model_input.to_dict(),
        }
        return IdentityEnvelope(
            current_node_key="current",
            candidate_node_key="candidate",
            candidate_reasons=("label_contains",),
            context_bindings=bindings,
            task_cache_key=_canonical_hash(hash_input),
            model_input=model_input,
        )

    def test_exact_and_whitespace_only_quotes_are_grounded(self) -> None:
        text = "萧熏儿，后来称作熏\n儿。"
        envelope = self._envelope(
            text,
            (IdentityContextBinding(text, SourceSpan(0, len(text)), "bridge"),),
        )
        decision = ground_identity_model_output(
            envelope,
            IdentityModelOutput.parse(
                {
                    "identity_relation": "same_character",
                    "label_relation": "alias",
                    "identity_evidence_quotes": ["称作熏儿"],
                }
            ),
            document_text=text,
        )
        self.assertEqual(decision.identity_relation, "same_character")
        self.assertEqual(decision.grounded_identity_evidence[0].evidence_quote, "称作熏\n儿")
        self.assertEqual(decision.grounded_identity_evidence[0].match_mode, "whitespace_equivalent")

    def test_non_whitespace_rewrite_and_ambiguous_occurrence_fail_closed(self) -> None:
        text = "她叫熏儿，她仍叫熏儿。"
        envelope = self._envelope(
            text,
            (IdentityContextBinding(text, SourceSpan(0, len(text)), "bridge"),),
        )
        rewritten = ground_identity_model_output(
            envelope,
            IdentityModelOutput.parse(
                {
                    "identity_relation": "same_character",
                    "label_relation": "alias",
                    "identity_evidence_quotes": ["她名叫熏儿"],
                }
            ),
            document_text=text,
        )
        self.assertEqual(rewritten.identity_relation, "uncertain")
        self.assertIn("identity_evidence_not_in_model_context", {issue.code for issue in rewritten.issues})
        ambiguous = ground_identity_model_output(
            envelope,
            IdentityModelOutput.parse(
                {
                    "identity_relation": "same_character",
                    "label_relation": "alias",
                    "identity_evidence_quotes": ["熏儿"],
                }
            ),
            document_text=text,
        )
        self.assertEqual(ambiguous.identity_relation, "uncertain")
        self.assertIn("ambiguous_identity_evidence", {issue.code for issue in ambiguous.issues})


class IdentityPreparationAndRegistryTests(unittest.TestCase):
    def test_same_label_is_only_a_candidate_and_candidate_count_is_bounded(self) -> None:
        text = "萧炎甲。萧炎乙。萧炎丙。萧炎丁。"
        nodes = tuple(
            _node(index=i, label="萧炎", text=text, context_span=span)
            for i, span in enumerate(
                (SourceSpan(0, 3), SourceSpan(4, 7), SourceSpan(8, 11), SourceSpan(12, 15)),
                start=1,
            )
        )
        preparation = build_identity_preparation(
            local_nodes=_document_nodes(text, *nodes),
            document_text=text,
            max_candidates_per_node=2,
        )
        self.assertEqual(preparation.deterministic_edges, ())
        counts: dict[str, int] = {}
        for envelope in preparation.envelopes:
            counts[envelope.current_node_key] = counts.get(envelope.current_node_key, 0) + 1
        self.assertLessEqual(max(counts.values()), 2)

    def test_shared_document_fact_is_the_only_deterministic_same_edge(self) -> None:
        text = "萧炎黑眸。少年黑眸。"
        shared = "a" * 64
        first = _node(
            index=1,
            label="萧炎",
            text=text,
            context_span=SourceSpan(0, 5),
            facts=(_fact(fact_hash=shared, quote="黑眸", span=SourceSpan(2, 4), value="黑"),),
        )
        second = _node(
            index=2,
            label="萧炎",
            text=text,
            context_span=SourceSpan(5, 10),
            facts=(_fact(fact_hash=shared, quote="黑眸", span=SourceSpan(7, 9), value="黑"),),
        )
        preparation = build_identity_preparation(
            local_nodes=_document_nodes(text, first, second), document_text=text
        )
        self.assertEqual(len(preparation.deterministic_edges), 1)
        self.assertEqual(preparation.envelopes, ())

    def test_same_relation_links_aliases_and_preserves_fact_conflicts(self) -> None:
        text = "萧熏儿眼睛明亮。熏儿眼睛幽深。"
        first = _node(
            index=1,
            label="萧熏儿",
            text=text,
            context_span=SourceSpan(0, 8),
            facts=(_fact(fact_hash="1" * 64, quote="眼睛明亮", span=SourceSpan(3, 7), value="明亮"),),
        )
        second = _node(
            index=2,
            label="熏儿",
            text=text,
            context_span=SourceSpan(8, 15),
            facts=(_fact(fact_hash="2" * 64, quote="眼睛幽深", span=SourceSpan(10, 14), value="幽深"),),
        )
        preparation = build_identity_preparation(
            local_nodes=_document_nodes(text, first, second),
            document_text=text,
            max_candidates_per_node=1,
        )
        envelope = preparation.envelopes[0]
        decision = GroundedIdentityDecision(
            current_node_key=envelope.current_node_key,
            candidate_node_key=envelope.candidate_node_key,
            task_cache_key=envelope.task_cache_key,
            requested_identity_relation="same_character",
            identity_relation="same_character",
            label_relation="alias",
            grounded_identity_evidence=(
                GroundedIdentityEvidence("熏儿", SourceSpan(8, 10), "exact"),
            ),
            issues=(),
        )
        registry = build_document_character_registry(
            preparation=preparation, grounded_decisions=(decision,)
        )
        self.assertEqual(registry["summary"]["global_characters"], 1)
        character = registry["characters"][0]
        self.assertEqual(len(character["appearance_fact_refs"]), 2)
        self.assertEqual(len(character["possible_conflicts"]), 1)
        self.assertEqual({item["label_quote"] for item in character["labels"]}, {"萧熏儿", "熏儿"})

    def test_different_same_name_creates_cannot_link_and_two_profiles(self) -> None:
        text = "张伟甲。张伟乙。"
        first = _node(index=1, label="张伟", text=text, context_span=SourceSpan(0, 3))
        second = _node(index=2, label="张伟", text=text, context_span=SourceSpan(4, 7))
        preparation = build_identity_preparation(
            local_nodes=_document_nodes(text, first, second), document_text=text
        )
        envelope = preparation.envelopes[0]
        decision = GroundedIdentityDecision(
            envelope.current_node_key,
            envelope.candidate_node_key,
            envelope.task_cache_key,
            "different_characters",
            "different_characters",
            None,
            (GroundedIdentityEvidence("张伟乙", SourceSpan(4, 7), "exact"),),
            (),
        )
        registry = build_document_character_registry(
            preparation=preparation, grounded_decisions=(decision,)
        )
        self.assertEqual(registry["summary"]["global_characters"], 2)
        self.assertEqual(registry["summary"]["cannot_link_constraints"], 1)
        self.assertTrue(all(not c["labels"][0]["globally_unique"] for c in registry["characters"]))

    def test_uncertain_binding_is_not_silently_promoted_to_a_profile(self) -> None:
        text = "萧炎甲。萧炎乙。"
        first = _node(index=1, label="萧炎", text=text, context_span=SourceSpan(0, 3))
        second = _node(index=2, label="萧炎", text=text, context_span=SourceSpan(4, 7))
        preparation = build_identity_preparation(
            local_nodes=_document_nodes(text, first, second), document_text=text
        )
        envelope = preparation.envelopes[0]
        decision = GroundedIdentityDecision(
            envelope.current_node_key,
            envelope.candidate_node_key,
            envelope.task_cache_key,
            "uncertain",
            "uncertain",
            None,
            (),
            (),
        )
        registry = build_document_character_registry(
            preparation=preparation, grounded_decisions=(decision,)
        )
        self.assertEqual(registry["summary"]["global_characters"], 1)
        self.assertEqual(registry["summary"]["unresolved_bindings"], 1)
        self.assertEqual(registry["summary"]["review_items"], 1)

    def test_identity_batch_writes_registry_and_resumes_saved_model_output(self) -> None:
        text = "萧炎甲。萧炎乙。"
        first = _node(index=1, label="萧炎", text=text, context_span=SourceSpan(0, 3))
        second = _node(index=2, label="萧炎", text=text, context_span=SourceSpan(4, 7))
        preparation = build_identity_preparation(
            local_nodes=_document_nodes(text, first, second), document_text=text
        )
        manifest = {
            "schema_version": "identity-preparation-manifest-v1",
            "source_document_version_id": "doc-v1",
            "document_hash": sha256_text(text),
            "source_artifacts": {},
            "configuration": {},
            "contracts": {},
        }
        provider = _Provider(
            {
                "identity_relation": "uncertain",
                "label_relation": None,
                "identity_evidence_quotes": [],
            }
        )
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            with mock.patch(
                "novel_character_generator.identity_batch._load_preparation",
                return_value=(preparation, manifest),
            ):
                first_summary = run_document_identity(
                    document_text=text,
                    source_n2_packets_file=Path("n2.json"),
                    source_n3_run_dir=Path("n3"),
                    document_evidence_file=Path("document.json"),
                    provider=provider,
                    output_dir=output,
                )
                second_summary = run_document_identity(
                    document_text=text,
                    source_n2_packets_file=Path("n2.json"),
                    source_n3_run_dir=Path("n3"),
                    document_evidence_file=Path("document.json"),
                    provider=_FailIfCalledProvider(),
                    output_dir=output,
                )
            self.assertTrue(first_summary["complete"])
            self.assertEqual(first_summary["new_provider_calls"], 1)
            self.assertEqual(second_summary["new_provider_calls"], 0)
            self.assertEqual(second_summary["resumed_tasks"], 1)
            self.assertTrue((output / "document-character-registry.json").exists())
            history = json.loads((output / "run-history.json").read_text(encoding="utf-8"))
            self.assertEqual(len(history), 2)


if __name__ == "__main__":
    unittest.main()
