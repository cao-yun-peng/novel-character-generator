import base64
import hashlib

from novel_character_generator.application.ports.image_generation import (
    ImageProviderCapabilities,
    ImageRemoteStatus,
    ImageSubmission,
    ImageSubmitRequest,
)

# Valid deterministic 1x1 PNG. The Mock Provider tests orchestration and
# persistence, not visual quality.
_MOCK_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


class MockImageProvider:
    provider = "mock"
    version = "mock-image-v1"
    prompt_renderer = "none"
    prompt_renderer_version = "none"

    async def submit(self, request: ImageSubmitRequest) -> ImageSubmission:
        fingerprint = hashlib.sha256(request.model_dump_json().encode()).hexdigest()
        return ImageSubmission(
            provider_request_id=f"mock-{fingerprint}",
            status="succeeded",
            artifact_refs=[f"mock-{fingerprint}"],
        )

    async def query(self, provider_request_id: str) -> ImageRemoteStatus:
        if not provider_request_id.startswith("mock-"):
            return ImageRemoteStatus(status="failed", error_code="mock_job_not_found")
        return ImageRemoteStatus(status="succeeded", artifact_refs=[provider_request_id])

    async def download(self, artifact_ref: str) -> bytes:
        if not artifact_ref.startswith("mock-"):
            raise ValueError("mock_artifact_not_found")
        return _MOCK_PNG

    def capabilities(self) -> ImageProviderCapabilities:
        return ImageProviderCapabilities(
            idempotency=True,
            cancellation=False,
            request_fingerprint_lookup=True,
            cost_reporting=False,
        )

    async def close(self) -> None:
        return None
