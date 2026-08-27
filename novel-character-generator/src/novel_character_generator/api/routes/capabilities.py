from fastapi import APIRouter
from pydantic import BaseModel

from novel_character_generator.settings import get_settings

router = APIRouter(prefix="/api/v1/capabilities", tags=["capabilities"])


class CapabilitiesResponse(BaseModel):
    source_formats: list[str]
    extraction: bool
    document_versioning: bool
    run_events_sse: bool
    external_operation_reconciliation: bool
    agent_runtime: bool
    human_approvals: bool
    story_temporal_binding: bool
    character_entity_resolution: bool
    appearance_aggregation: bool
    evaluation_framework: bool
    retrieval_lexical_index: bool
    retrieval_hybrid_index: bool
    visual_enrichment: bool
    image_generation: bool
    raw_model_response_viewer: bool


@router.get("", response_model=CapabilitiesResponse)
async def capabilities() -> CapabilitiesResponse:
    settings = get_settings()
    return CapabilitiesResponse(
        source_formats=["txt"],
        extraction=True,
        document_versioning=True,
        run_events_sse=True,
        external_operation_reconciliation=False,
        agent_runtime=settings.agent_runtime_enabled,
        human_approvals=True,
        story_temporal_binding=True,
        character_entity_resolution=True,
        appearance_aggregation=True,
        evaluation_framework=True,
        retrieval_lexical_index=True,
        retrieval_hybrid_index=settings.embedding_provider != "disabled",
        visual_enrichment=settings.embedding_provider != "disabled",
        image_generation=settings.image_provider != "disabled",
        raw_model_response_viewer=(
            settings.app_env == "development"
            and settings.llm_raw_response_capture_enabled
        ),
    )
