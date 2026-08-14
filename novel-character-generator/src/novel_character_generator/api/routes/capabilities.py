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
    evaluation_framework: bool
    image_generation: bool


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
        evaluation_framework=True,
        image_generation=False,
    )
