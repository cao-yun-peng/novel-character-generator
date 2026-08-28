from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from novel_character_generator.domain.entities.image import FieldSourceRef, ImageRenderSpec


class ImageProviderSubmissionRejected(RuntimeError):
    """The provider definitively rejected a request before creating a job."""


class ImageSubmitRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    context_hash: str = Field(min_length=64, max_length=64)
    workflow_profile: str
    workflow_version: str
    candidate_index: int = Field(ge=0)
    seed: int = Field(ge=0)
    render_spec: ImageRenderSpec


class ImageSubmission(BaseModel):
    provider_request_id: str
    status: Literal["submitted", "succeeded"]
    artifact_refs: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_completed_submission(self) -> "ImageSubmission":
        if self.status == "succeeded" and not self.artifact_refs:
            raise ValueError("succeeded_image_submission_requires_artifact_refs")
        return self


class ImageRemoteStatus(BaseModel):
    status: Literal["submitted", "running", "succeeded", "failed"]
    artifact_refs: list[str] = Field(default_factory=list)
    error_code: str | None = None


class ImageProviderCapabilities(BaseModel):
    idempotency: bool
    cancellation: bool
    request_fingerprint_lookup: bool
    cost_reporting: bool


PromptPolarity = Literal["positive", "negative"]
PromptBlock = Literal[
    "instruction",
    "identity",
    "stage",
    "outfit",
    "performance",
    "environment",
    "art_direction",
    "negative",
]


class PromptSourceBinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field_path: str = Field(min_length=1)
    source_refs: list[FieldSourceRef] = Field(min_length=1)


class RenderedPromptClause(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1)
    polarity: PromptPolarity
    block: PromptBlock
    source_bindings: list[PromptSourceBinding] = Field(default_factory=list)


class RenderedImagePrompt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    renderer: str = Field(min_length=1)
    version: str = Field(min_length=1)
    positive_prompt: str = Field(min_length=1)
    negative_prompt: str = ""
    clauses: list[RenderedPromptClause] = Field(min_length=1)


class ImagePromptRenderer(Protocol):
    renderer: str
    version: str

    def render(self, spec: ImageRenderSpec) -> RenderedImagePrompt: ...


class ImageProvider(Protocol):
    provider: str
    version: str
    prompt_renderer: str
    prompt_renderer_version: str

    async def submit(self, request: ImageSubmitRequest) -> ImageSubmission: ...

    async def query(self, provider_request_id: str) -> ImageRemoteStatus: ...

    async def download(self, artifact_ref: str) -> bytes: ...

    def capabilities(self) -> ImageProviderCapabilities: ...

    async def close(self) -> None: ...
