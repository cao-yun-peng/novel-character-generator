from typing import Literal

from pydantic import BaseModel, Field


class ModelTokenUsage(BaseModel):
    input_tokens: int = Field(default=0, ge=0)
    cache_hit_tokens: int = Field(default=0, ge=0)
    cache_miss_tokens: int = Field(default=0, ge=0)
    reasoning_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)


class ModelCallMetadata(BaseModel):
    wire_api: Literal["chat_completions", "responses"]
    provider_request_id: str | None = None
    response_model: str | None = None
    status: str
    finish_reason: str | None = None
    attempts: int = Field(default=1, ge=1)
    latency_ms: float = Field(ge=0)
    usage: ModelTokenUsage = Field(default_factory=ModelTokenUsage)
