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
    build_document_character_registry,
    build_document_local_character_nodes,
    build_identity_preparation,
    ground_identity_model_output,
)
from .identity_batch import prepare_document_identity, run_document_identity
from .document_evidence import build_document_character_evidence, run_document_evidence_aggregation
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
    "GroundingResult",
    "DocumentLocalCharacterNodes",
    "GroundedIdentityDecision",
    "IdentityEnvelope",
    "IdentityModelOutput",
    "IdentityOrchestrator",
    "IdentityPreparation",
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
    "SourceSpan",
    "build_document_chunk_manifest",
    "build_document_character_evidence",
    "build_document_character_registry",
    "build_document_local_character_nodes",
    "build_identity_preparation",
    "build_m2_attribution_envelopes",
    "ground_m1_result",
    "ground_identity_model_output",
    "prepare_document_identity",
    "run_m1_document",
    "run_m2_from_m1_run",
    "run_document_evidence_aggregation",
    "run_document_identity",
    "resolve_n3_chunk",
    "run_n3_promotion_from_m2_run",
    "replay_promotion_grounding",
    "sha256_text",
]
