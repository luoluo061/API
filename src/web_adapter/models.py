from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    provider: Literal["doubao"]
    prompt: str = Field(min_length=1, max_length=40000)
    session_id: str | None = Field(default=None, max_length=128)
    timeout_seconds: int | None = Field(default=None, ge=5, le=600)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProfileVerifyRequest(BaseModel):
    provider: Literal["doubao"]
    timeout_seconds: int | None = Field(default=None, ge=5, le=120)


class ErrorPayload(BaseModel):
    code: str
    message: str
    retryable: bool
    detail: str | None = None


class ArtifactPayload(BaseModel):
    screenshot_path: str | None = None
    html_snapshot_path: str | None = None
    trace_path: str | None = None
    request_log_path: str | None = None
    runtime_profile_path: str | None = None
    page_url: str | None = None
    retry_count: int = 0


class ChatResponse(BaseModel):
    request_id: str
    provider: str
    status: Literal["ok", "error"]
    content: str | None = None
    usage_like_meta: dict[str, Any] = Field(default_factory=dict)
    artifacts: ArtifactPayload = Field(default_factory=ArtifactPayload)
    error: ErrorPayload | None = None


class ProfileVerifyResponse(BaseModel):
    request_id: str
    provider: str
    status: Literal["ok", "error"]
    login_state: Literal["logged_in", "login_required", "unknown"]
    artifacts: ArtifactPayload = Field(default_factory=ArtifactPayload)
    error: ErrorPayload | None = None


class HealthComponent(BaseModel):
    status: Literal["ok", "warn", "error"]
    detail: str | None = None


class HealthResponse(BaseModel):
    service: HealthComponent
    browser: HealthComponent
    master_profile: HealthComponent
    runtime_profile_root: HealthComponent
    provider: HealthComponent
    queue_depth: int
    browser_channel: str | None
    mock_mode: bool
