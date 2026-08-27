from typing import Literal, Protocol

from pydantic import BaseModel, Field


class ImageSubmitRequest(BaseModel):
    context_hash: str = Field(min_length=64, max_length=64)
    workflow_profile: str
    workflow_version: str
    candidate_index: int = Field(ge=0)
    seed: int = Field(ge=0)
    context_payload: dict[str, object]


class ImageSubmission(BaseModel):
    provider_request_id: str
    status: Literal["submitted", "succeeded"]


class ImageRemoteStatus(BaseModel):
    status: Literal["submitted", "running", "succeeded", "failed"]
    artifact_refs: list[str] = Field(default_factory=list)
    error_code: str | None = None


class ImageProviderCapabilities(BaseModel):
    idempotency: bool
    cancellation: bool
    request_fingerprint_lookup: bool
    cost_reporting: bool


class ImageProvider(Protocol):
    provider: str
    version: str

    async def submit(self, request: ImageSubmitRequest) -> ImageSubmission: ...

    async def query(self, provider_request_id: str) -> ImageRemoteStatus: ...

    async def download(self, artifact_ref: str) -> bytes: ...

    def capabilities(self) -> ImageProviderCapabilities: ...
