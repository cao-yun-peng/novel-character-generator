import copy
import json
import tempfile
import unittest
from hashlib import sha256
from pathlib import Path
from unittest import mock

from novel_character_generator.identity import (
    DocumentLocalCharacterNodes,
    GroundedIdentityDecision,
    IdentityAppearanceFactRef,
    IdentityContextBinding,
    IdentityPreparation,
    LocalCharacterNode,
    build_document_character_registry,
    build_identity_preparation,
)
from novel_character_generator.identity_rescue import (
    ClusterCandidateBinding,
    ClusterCandidateModelInput,
    ClusterCharacterModelInput,
    ClusterIdentityRescueOrchestrator,
    ClusterRelationshipBinding,
    ClusterRescueEnvelope,
    ClusterRescueModelInput,
    ClusterRescueModelOutput,
    ClusterRescuePreparation,
    build_cluster_rescue_preparation,
    ground_cluster_rescue_output,
)
from novel_character_generator.identity_rescue_batch import run_identity_rescue
from novel_character_generator.text import SourceSpan, sha256_text


def _canonical_hash(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(payload.encode("utf-8")).hexdigest()


def _node(index: int, label: str, text: str, span: SourceSpan) -> LocalCharacterNode:
    source_ref = {
        "source_document_version_id": "doc-v1",
        "chunk_id": f"chunk-{index}",
        "local_mention_id": f"m{index}",
        "mention_type": "exact",
        "packet_hash": f"{index:064x}",
    }
    node_key = _canonical_hash({"ref_type": "local", "source_character_ref": source_ref})
    fact_quote = "黑色短发"
    return LocalCharacterNode(
        node_key=node_key,
        ref_type="local",
        source_character_ref=source_ref,
        character_origin="exact",
        label_quote=label,
        label_type="exact",
        chunk_id=f"chunk-{index}",
        chunk_source_span=span,
        context_bindings=(IdentityContextBinding(span.quote(text), span, "node"),),
        appearance_fact_refs=(
            IdentityAppearanceFactRef(
                fact_hash=f"{index + 10:064x}",
                fact_quote=fact_quote,
                category="hair",
                attribute="发色",
                value="黑色",
                document_fact_span=SourceSpan(text.index("黑色短发"), text.index("黑色短发") + 4),
            ),
        ),
        order_position=span.start,
    )


def _rescue_envelope(text: str) -> ClusterRescueEnvelope:
    model_input = ClusterRescueModelInput(
        current_character=ClusterCharacterModelInput(
            ("小三",),
            ("小三有黑色短发。",),
            ("黑色短发",),
        ),
        candidate_characters=(
            ClusterCandidateModelInput(
                1,
                ("唐三",),
                ("唐三有黑色短发。",),
                ("黑色短发",),
                (text,),
            ),
        ),
    )
    candidate = ClusterCandidateBinding(1, "char-candidate", "candidate-node", ("base_pair_uncertain",))
    hash_input = {
        "schema_version": "m3-cluster-rescue-envelope-v1",
        "policy_version": "residual-cluster-adjudication-v2",
        "context_version": "candidate-specific-relationship-context-v1",
        "subject_character_id": "char-subject",
        "subject_anchor_node_key": "subject-node",
        "candidate_bindings": [candidate.to_dict()],
        "model_input": model_input.to_dict(),
    }
    return ClusterRescueEnvelope(
        "char-subject",
        "subject-node",
        (candidate,),
        (ClusterRelationshipBinding(1, text, SourceSpan(0, len(text))),),
        _canonical_hash(hash_input),
        model_input,
    )


class _Provider:
    def __init__(self, output):
        self.output = output
        self.requests = []

    def generate(self, request):
        self.requests.append(request)
        return self.output


class _FailProvider:
    def generate(self, request):
        raise AssertionError("resumed cluster rescue task must not call Provider")


class ClusterRescueBoundaryTests(unittest.TestCase):
    def test_model_evidence_must_come_from_selected_relationship_context(self) -> None:
        text = "唐三被父亲叫作小三。"
        envelope = _rescue_envelope(text)
        accepted = ground_cluster_rescue_output(
            envelope,
            ClusterRescueModelOutput.parse(
                {
                    "identity_relation": "same_character",
                    "candidate_number": 1,
                    "label_relation": "alias",
                    "identity_evidence_quotes": ["唐三被父亲叫作小三"],
                },
                candidate_count=1,
            ),
            document_text=text,
        )
        self.assertEqual(accepted.identity_relation, "same_character")
        self.assertEqual(accepted.grounded_identity_evidence[0].evidence_quote, "唐三被父亲叫作小三")

        rejected = ground_cluster_rescue_output(
            envelope,
            ClusterRescueModelOutput.parse(
                {
                    "identity_relation": "same_character",
                    "candidate_number": 1,
                    "label_relation": "alias",
                    "identity_evidence_quotes": ["小三有黑色短发"],
                },
                candidate_count=1,
            ),
            document_text=text,
        )
        self.assertEqual(rejected.identity_relation, "uncertain")
        self.assertIn(
            "identity_evidence_not_in_relationship_context",
            {issue.code for issue in rejected.issues},
        )

    def test_label_only_quote_is_rejected_even_when_grounded(self) -> None:
        text = "唐三被父亲叫作小三。"
        decision = ground_cluster_rescue_output(
            _rescue_envelope(text),
            ClusterRescueModelOutput.parse(
                {
                    "identity_relation": "same_character",
                    "candidate_number": 1,
                    "label_relation": "alias",
                    "identity_evidence_quotes": ["小三"],
                },
                candidate_count=1,
            ),
            document_text=text,
        )
        self.assertEqual(decision.identity_relation, "uncertain")
        self.assertIn("identity_evidence_is_only_a_label", {issue.code for issue in decision.issues})

    def test_orchestrator_payload_contains_no_internal_identity_fields(self) -> None:
        text = "唐三被父亲叫作小三。"
        provider = _Provider(
            {
                "identity_relation": "same_character",
                "candidate_number": 1,
                "label_relation": "alias",
                "identity_evidence_quotes": ["唐三被父亲叫作小三"],
            }
        )
        decision = ClusterIdentityRescueOrchestrator(provider).run(
            _rescue_envelope(text),
            document_text=text,
        )
        self.assertEqual(decision.identity_relation, "same_character")
        payload = json.dumps(provider.requests[0].user_payload, ensure_ascii=False)
        for forbidden in ("node_key", "character_id", "span", "hash", "ref", "cache"):
            self.assertNotIn(forbidden, payload)


class ClusterRescuePreparationTests(unittest.TestCase):
    def _prepared_case(self):
        text = "唐三被父亲叫作小三，留着黑色短发。"
        first = _node(1, "唐三", text, SourceSpan(0, len(text)))
        second = _node(2, "小三", text, SourceSpan(0, len(text)))
        local_nodes = DocumentLocalCharacterNodes("doc-v1", sha256_text(text), (first, second))
        preparation = build_identity_preparation(
            local_nodes=local_nodes,
            document_text=text,
            max_candidates_per_node=1,
        )
        self.assertEqual(len(preparation.envelopes), 1)
        base_envelope = preparation.envelopes[0]
        base_decision = GroundedIdentityDecision(
            base_envelope.current_node_key,
            base_envelope.candidate_node_key,
            base_envelope.task_cache_key,
            "uncertain",
            "uncertain",
            None,
            (),
            (),
        )
        baseline = build_document_character_registry(
            preparation=preparation,
            grounded_decisions=(base_decision,),
        )
        rescue = build_cluster_rescue_preparation(
            preparation=preparation,
            grounded_decisions=(base_decision,),
            baseline_registry=baseline,
            document_text=text,
        )
        return text, preparation, base_decision, baseline, rescue

    def test_rescue_preparation_and_supplemental_merge(self) -> None:
        text, preparation, base_decision, _, rescue = self._prepared_case()
        self.assertEqual(len(rescue.envelopes), 1)
        envelope = rescue.envelopes[0]
        self.assertTrue(envelope.model_input.candidate_characters[0].relationship_context_quotes)
        for binding in envelope.relationship_bindings:
            self.assertEqual(binding.document_span.quote(text), binding.context_quote)

        grounded = ground_cluster_rescue_output(
            envelope,
            ClusterRescueModelOutput.parse(
                {
                    "identity_relation": "same_character",
                    "candidate_number": 1,
                    "label_relation": "alias",
                    "identity_evidence_quotes": ["唐三被父亲叫作小三"],
                },
                candidate_count=1,
            ),
            document_text=text,
        )
        final = build_document_character_registry(
            preparation=preparation,
            grounded_decisions=(base_decision,),
            supplemental_grounded_decisions=(grounded.to_supplemental_decision(),),
        )
        self.assertEqual(final["summary"]["global_characters"], 1)
        self.assertEqual(final["summary"]["unresolved_bindings"], 0)
        self.assertEqual(final["summary"]["appearance_fact_refs"], 2)

    def test_reverse_cluster_proposals_are_deduplicated_as_one_unordered_pair(self) -> None:
        text, preparation, base_decision, baseline, _ = self._prepared_case()
        characters = baseline["characters"]
        self.assertEqual(len(characters), 2)
        reverse = {
            "source_character_ref": characters[0]["member_character_refs"][0],
            "label_quote": characters[0]["canonical_label"],
            "candidate_character_ids": [characters[1]["character_id"]],
            "reason_code": "insufficient_identity_evidence",
            "review_item_id": "reverse-test",
        }
        baseline_with_reverse = copy.deepcopy(baseline)
        baseline_with_reverse["unresolved_bindings"].append(reverse)
        rescue = build_cluster_rescue_preparation(
            preparation=preparation,
            grounded_decisions=(base_decision,),
            baseline_registry=baseline_with_reverse,
            document_text=text,
        )
        self.assertEqual(len(rescue.envelopes), 1)
        self.assertEqual(len(rescue.envelopes[0].candidate_bindings), 1)

    def test_rescue_batch_writes_registry_and_resumes(self) -> None:
        text, preparation, base_decision, _, rescue = self._prepared_case()
        manifest = {
            "schema_version": "cluster-rescue-manifest-v1",
            "source_document_version_id": "doc-v1",
            "document_hash": sha256_text(text),
            "source_artifacts": {},
            "configuration": {},
            "contracts": {},
        }
        output_value = {
            "identity_relation": "same_character",
            "candidate_number": 1,
            "label_relation": "alias",
            "identity_evidence_quotes": ["唐三被父亲叫作小三"],
        }
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            with mock.patch(
                "novel_character_generator.identity_rescue_batch._build_preparation",
                return_value=(preparation, (base_decision,), rescue, manifest),
            ):
                first = run_identity_rescue(
                    document_text=text,
                    source_identity_run_dir=Path("identity"),
                    provider=_Provider(output_value),
                    output_dir=output,
                )
                second = run_identity_rescue(
                    document_text=text,
                    source_identity_run_dir=Path("identity"),
                    provider=_FailProvider(),
                    output_dir=output,
                )
        self.assertTrue(first["complete"])
        self.assertEqual(first["new_provider_calls"], 1)
        self.assertEqual(second["new_provider_calls"], 0)
        self.assertEqual(second["resumed_tasks"], 1)
        self.assertEqual(second["registry_summary"]["global_characters"], 1)

    def test_rescue_batch_reuses_seeded_grounded_decision_without_provider_call(self) -> None:
        text, preparation, base_decision, _, rescue = self._prepared_case()
        envelope = rescue.envelopes[0]
        seeded = ground_cluster_rescue_output(
            envelope,
            ClusterRescueModelOutput.parse(
                {
                    "identity_relation": "same_character",
                    "candidate_number": 1,
                    "label_relation": "alias",
                    "identity_evidence_quotes": ["唐三被父亲叫作小三"],
                },
                candidate_count=1,
            ),
            document_text=text,
        )
        manifest = {
            "schema_version": "cluster-rescue-manifest-v1",
            "source_document_version_id": "doc-v1",
            "document_hash": sha256_text(text),
            "source_artifacts": {},
            "configuration": {},
            "contracts": {},
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            seed_dir = root / "seed"
            seed_dir.mkdir()
            (seed_dir / "grounded-cluster-rescue-decisions.json").write_text(
                json.dumps([seeded.to_dict()], ensure_ascii=False),
                encoding="utf-8",
            )
            with mock.patch(
                "novel_character_generator.identity_rescue_batch._build_preparation",
                return_value=(preparation, (base_decision,), rescue, manifest),
            ):
                summary = run_identity_rescue(
                    document_text=text,
                    source_identity_run_dir=Path("identity"),
                    seed_rescue_run_dir=seed_dir,
                    provider=_FailProvider(),
                    output_dir=root / "output",
                )
        self.assertTrue(summary["complete"])
        self.assertTrue(summary["fixed_point_reached"])
        self.assertEqual(summary["seeded_decisions"], 1)
        self.assertEqual(summary["planned_tasks"], 0)
        self.assertEqual(summary["new_provider_calls"], 0)
        self.assertEqual(summary["registry_summary"]["global_characters"], 1)

    def test_rescue_batch_iterates_until_three_clusters_form_one_component(self) -> None:
        text = "唐三被父亲叫作小三，后来仍被称为唐三。黑色短发。"
        nodes = (
            _node(1, "唐三", text, SourceSpan(0, len(text))),
            _node(2, "小三", text, SourceSpan(0, len(text))),
            _node(3, "唐三", text, SourceSpan(0, len(text))),
        )
        preparation = IdentityPreparation(
            DocumentLocalCharacterNodes("doc-v1", sha256_text(text), nodes),
            (),
            (),
        )
        baseline = build_document_character_registry(
            preparation=preparation,
            grounded_decisions=(),
        )

        def rescue_envelope(
            *,
            subject_id: str,
            subject_node: LocalCharacterNode,
            subject_label: str,
            candidate_id: str,
            candidate_node: LocalCharacterNode,
            candidate_label: str,
        ) -> ClusterRescueEnvelope:
            model_input = ClusterRescueModelInput(
                ClusterCharacterModelInput((subject_label,), (text,), ("黑色短发",)),
                (
                    ClusterCandidateModelInput(
                        1,
                        (candidate_label,),
                        (text,),
                        ("黑色短发",),
                        (text,),
                    ),
                ),
            )
            binding = ClusterCandidateBinding(
                1,
                candidate_id,
                candidate_node.node_key,
                ("registry_unresolved",),
            )
            hash_input = {
                "schema_version": "m3-cluster-rescue-envelope-v1",
                "policy_version": "residual-cluster-adjudication-v2",
                "context_version": "candidate-specific-relationship-context-v1",
                "subject_character_id": subject_id,
                "subject_anchor_node_key": subject_node.node_key,
                "candidate_bindings": [binding.to_dict()],
                "model_input": model_input.to_dict(),
            }
            return ClusterRescueEnvelope(
                subject_id,
                subject_node.node_key,
                (binding,),
                (ClusterRelationshipBinding(1, text, SourceSpan(0, len(text))),),
                _canonical_hash(hash_input),
                model_input,
            )

        first_rescue = ClusterRescuePreparation(
            baseline,
            (
                rescue_envelope(
                    subject_id="char-a",
                    subject_node=nodes[0],
                    subject_label="唐三",
                    candidate_id="char-b",
                    candidate_node=nodes[1],
                    candidate_label="小三",
                ),
            ),
        )
        second_rescue = ClusterRescuePreparation(
            baseline,
            (
                rescue_envelope(
                    subject_id="char-ab",
                    subject_node=nodes[0],
                    subject_label="唐三/小三",
                    candidate_id="char-c",
                    candidate_node=nodes[2],
                    candidate_label="唐三",
                ),
            ),
        )
        empty_rescue = ClusterRescuePreparation(baseline, ())
        manifest = {
            "schema_version": "cluster-rescue-manifest-v1",
            "source_document_version_id": "doc-v1",
            "document_hash": sha256_text(text),
            "source_artifacts": {},
            "configuration": {},
            "contracts": {},
        }
        provider = _Provider(
            {
                "identity_relation": "same_character",
                "candidate_number": 1,
                "label_relation": "name_variant",
                "identity_evidence_quotes": ["唐三被父亲叫作小三，后来仍被称为唐三"],
            }
        )
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch(
                "novel_character_generator.identity_rescue_batch._build_preparation",
                return_value=(preparation, (), first_rescue, manifest),
            ), mock.patch(
                "novel_character_generator.identity_rescue_batch.build_cluster_rescue_preparation",
                side_effect=(second_rescue, empty_rescue),
            ):
                summary = run_identity_rescue(
                    document_text=text,
                    source_identity_run_dir=Path("identity"),
                    provider=provider,
                    output_dir=Path(directory),
                )
        self.assertEqual(len(provider.requests), 2)
        self.assertEqual(summary["rounds_completed"], 2)
        self.assertTrue(summary["fixed_point_reached"])
        self.assertEqual(summary["termination_reason"], "no_pending_tasks")
        self.assertEqual(summary["registry_summary"]["global_characters"], 1)


if __name__ == "__main__":
    unittest.main()
