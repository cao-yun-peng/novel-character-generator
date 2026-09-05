"""Novel Character Generator runtime."""

from .chunking import (
    ChunkManifestEntry,
    DocumentChunkManifest,
    build_document_chunk_manifest,
)
from .grounding import GroundingResult, ground_m1_result
from .identity import (
    DocumentLocalCharacterNodes,
    GroundedIdentityDecision,
    IdentityEnvelope,
    IdentityModelOutput,
    IdentityOrchestrator,
    IdentityPreparation,
    apply_local_coreference_to_preparation,
    build_document_character_registry,
    build_document_local_character_nodes,
    build_identity_preparation,
    build_local_coreference_edges,
    ground_identity_model_output,
)
from .identity_batch import prepare_document_identity, run_document_identity
from .identity_local_closure import run_local_identity_closure_replay
from .identity_rescue import (
    ClusterIdentityRescueOrchestrator,
    ClusterRescueEnvelope,
    ClusterRescueModelOutput,
    build_cluster_rescue_preparation,
    ground_cluster_rescue_output,
)
from .identity_rescue_batch import prepare_identity_rescue, run_identity_rescue
from .label_review_projection import (
    DOCUMENT_LABEL_REVIEW_PROJECTION_VERSION,
    LABEL_PROJECTION_POLICY_VERSION,
    REVIEW_PROJECTION_POLICY_VERSION,
    build_document_label_review_projection,
    run_document_label_review_projection,
)
from .render_profile_compiler import (
    FACT_APPLICABILITY_POLICY_VERSION,
    RENDER_PROFILE_COMPILER_POLICY_VERSION,
    RENDER_PROFILE_REQUESTS_VERSION,
    RENDER_READY_CHARACTER_PROFILES_VERSION,
    build_render_ready_character_profiles,
    run_render_ready_character_profiles,
)
from .document_evidence import build_document_character_evidence, run_document_evidence_aggregation
from .document_profiles import build_document_character_profiles, run_document_profile_assembly
from .fact_groups import (
    build_document_character_fact_groups,
    run_document_fact_group_assembly,
)
from .appearance_scope import (
    build_document_character_appearance_scopes,
    parse_document_chapters,
    run_document_appearance_scope_assembly,
)
from .appearance_semantic_relations import (
    APPEARANCE_PROPOSITION_POLICY_VERSION,
    APPEARANCE_RELATION_POLICY_VERSION,
    build_appearance_semantic_projection,
)
from .appearance_state_segments import (
    STATE_SEGMENT_POLICY_VERSION,
    attach_transition_ids,
    build_character_state_segments,
    scene_expiry_position,
    transition_effective_position,
)
from .appearance_transition import (
    AppearanceTransitionProviderRequest,
    AppearanceTransitionChunk,
    WindowCharacter,
    build_appearance_transition_chunks,
    build_transition_request,
    deduplicate_grounded_transitions,
    ground_transition_events,
    materialize_appearance_states,
    parse_transition_model_output,
)
from .appearance_transition_batch import (
    prepare_document_appearance_transitions,
    run_document_appearance_transitions,
)
from .m1 import (
    M1OrchestrationEnvelope,
    M1Orchestrator,
    M1Provider,
    M1ProviderRequest,
)
from .m1_batch import run_m1_document
from .m2 import (
    M2AttributionOrchestrator,
    M2GroundedAttributionResult,
    M2GroundedPromotionResult,
    M2OrchestrationEnvelope,
    M2PromotionEnvelope,
    M2PromotionOrchestrator,
    build_m2_attribution_envelopes,
)
from .m2_batch import run_m2_from_m1_run
from .n3 import N3ChunkResolutionResult, N3DescribePoolResult, N3TargetAppearancePacket, resolve_n3_chunk
from .n3_batch import run_n3_promotion_from_m2_run
from .providers import DeepSeekCallTrace, DeepSeekConfig, DeepSeekProvider, DeepSeekUsage
from .promotion_replay import replay_promotion_grounding
from .text import SourceSpan, sha256_text

__all__ = [
    "ChunkManifestEntry",
    "DocumentChunkManifest",
    "DeepSeekCallTrace",
    "DeepSeekConfig",
    "DeepSeekProvider",
    "DeepSeekUsage",
    "DOCUMENT_LABEL_REVIEW_PROJECTION_VERSION",
    "FACT_APPLICABILITY_POLICY_VERSION",
    "GroundingResult",
    "DocumentLocalCharacterNodes",
    "GroundedIdentityDecision",
    "IdentityEnvelope",
    "IdentityModelOutput",
    "IdentityOrchestrator",
    "IdentityPreparation",
    "LABEL_PROJECTION_POLICY_VERSION",
    "ClusterIdentityRescueOrchestrator",
    "ClusterRescueEnvelope",
    "ClusterRescueModelOutput",
    "M1OrchestrationEnvelope",
    "M1Orchestrator",
    "M1Provider",
    "M1ProviderRequest",
    "M2AttributionOrchestrator",
    "M2GroundedAttributionResult",
    "M2GroundedPromotionResult",
    "M2OrchestrationEnvelope",
    "M2PromotionEnvelope",
    "M2PromotionOrchestrator",
    "N3ChunkResolutionResult",
    "N3DescribePoolResult",
    "N3TargetAppearancePacket",
    "REVIEW_PROJECTION_POLICY_VERSION",
    "RENDER_PROFILE_COMPILER_POLICY_VERSION",
    "RENDER_PROFILE_REQUESTS_VERSION",
    "RENDER_READY_CHARACTER_PROFILES_VERSION",
    "SourceSpan",
    "APPEARANCE_PROPOSITION_POLICY_VERSION",
    "APPEARANCE_RELATION_POLICY_VERSION",
    "STATE_SEGMENT_POLICY_VERSION",
    "AppearanceTransitionProviderRequest",
    "AppearanceTransitionChunk",
    "WindowCharacter",
    "apply_local_coreference_to_preparation",
    "build_document_chunk_manifest",
    "build_document_character_evidence",
    "build_document_character_profiles",
    "build_document_character_fact_groups",
    "build_document_character_appearance_scopes",
    "build_document_label_review_projection",
    "build_render_ready_character_profiles",
    "build_appearance_semantic_projection",
    "build_character_state_segments",
    "build_appearance_transition_chunks",
    "build_transition_request",
    "attach_transition_ids",
    "deduplicate_grounded_transitions",
    "build_document_character_registry",
    "build_document_local_character_nodes",
    "build_identity_preparation",
    "build_local_coreference_edges",
    "build_cluster_rescue_preparation",
    "build_m2_attribution_envelopes",
    "ground_m1_result",
    "ground_identity_model_output",
    "ground_cluster_rescue_output",
    "ground_transition_events",
    "materialize_appearance_states",
    "parse_transition_model_output",
    "prepare_document_appearance_transitions",
    "prepare_document_identity",
    "prepare_identity_rescue",
    "run_m1_document",
    "run_m2_from_m1_run",
    "run_document_evidence_aggregation",
    "run_document_profile_assembly",
    "run_document_fact_group_assembly",
    "run_document_appearance_scope_assembly",
    "run_document_label_review_projection",
    "run_render_ready_character_profiles",
    "run_document_appearance_transitions",
    "run_document_identity",
    "run_local_identity_closure_replay",
    "run_identity_rescue",
    "resolve_n3_chunk",
    "run_n3_promotion_from_m2_run",
    "replay_promotion_grounding",
    "sha256_text",
    "scene_expiry_position",
    "transition_effective_position",
    "parse_document_chapters",
]

from .character_snapshot import build_character_snapshot, run_character_snapshot, snapshot_to_render_profile
__all__ += ["build_character_snapshot", "run_character_snapshot", "snapshot_to_render_profile"]

from .automatic_semantics import run_automatic_semantics
__all__ += ["run_automatic_semantics"]
