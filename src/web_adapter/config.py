from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, Field


class Settings(BaseModel):
    app_name: str = "web-llm-adapter"
    host: str = "127.0.0.1"
    port: int = 8000
    base_url: str = "https://www.doubao.com/chat/"
    master_profile_dir: Path = Path(".profiles/masters/doubao-edge")
    runtime_profile_root: Path = Path(".profiles/runtime/doubao-edge")
    artifact_dir: Path = Path(".artifacts")
    browser_mode: str = Field(default="cdp", pattern="^(launch|cdp)$")
    browser_channel: str | None = "msedge"
    cdp_url: str = "http://127.0.0.1:9222"
    headless: bool = True
    trace_mode: str = Field(default="failure", pattern="^(off|failure|always)$")
    request_timeout_seconds: int = Field(default=90, ge=5, le=600)
    queue_wait_seconds: int = Field(default=30, ge=1, le=600)
    mock_mode: bool = False
    startup_browser_check: bool = False
    profile_mode: str = Field(default="dedicated", pattern="^(dedicated|clone)$")
    runtime_profile_retention: str = Field(
        default="success_delete_failure_keep",
        pattern="^(success_delete_failure_keep|delete_all|keep_all)$",
    )
    kill_residual_browser: bool = False

    doubao_input_selector: str = "textarea, div[contenteditable='true']"
    doubao_send_selector: str = (
        "button[data-testid='send-button'], "
        "button[type='submit'], "
        "button[aria-label='\\u53d1\\u9001'], "
        "button[aria-label='Send']"
    )
    doubao_response_selector: str = "[data-testid='message-content'], .message-content, .answer-content"
    doubao_login_indicators: tuple[str, ...] = (
        "button:has-text('\\u767b\\u5f55')",
        "[href*='login']",
        "[data-testid='login']",
        "input[type='password']",
    )


def _read_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def load_settings() -> Settings:
    return Settings(
        app_name=os.getenv("WEB_LLM_APP_NAME", "web-llm-adapter"),
        host=os.getenv("WEB_LLM_HOST", "127.0.0.1"),
        port=int(os.getenv("WEB_LLM_PORT", "8000")),
        base_url=os.getenv("WEB_LLM_BASE_URL", "https://www.doubao.com/chat/"),
        master_profile_dir=Path(os.getenv("WEB_LLM_MASTER_PROFILE_DIR", ".profiles/masters/doubao-edge")),
        runtime_profile_root=Path(os.getenv("WEB_LLM_RUNTIME_PROFILE_ROOT", ".profiles/runtime/doubao-edge")),
        artifact_dir=Path(os.getenv("WEB_LLM_ARTIFACT_DIR", ".artifacts")),
        browser_mode=os.getenv("WEB_LLM_BROWSER_MODE", "cdp"),
        browser_channel=os.getenv("WEB_LLM_BROWSER_CHANNEL", "msedge"),
        cdp_url=os.getenv("WEB_LLM_CDP_URL", "http://127.0.0.1:9222"),
        headless=_read_bool("WEB_LLM_HEADLESS", True),
        trace_mode=os.getenv("WEB_LLM_TRACE_MODE", "failure"),
        request_timeout_seconds=int(os.getenv("WEB_LLM_REQUEST_TIMEOUT_SECONDS", "90")),
        queue_wait_seconds=int(os.getenv("WEB_LLM_QUEUE_WAIT_SECONDS", "30")),
        mock_mode=_read_bool("WEB_LLM_MOCK_MODE", False),
        startup_browser_check=_read_bool("WEB_LLM_STARTUP_BROWSER_CHECK", False),
        profile_mode=os.getenv("WEB_LLM_PROFILE_MODE", "dedicated"),
        runtime_profile_retention=os.getenv(
            "WEB_LLM_RUNTIME_PROFILE_RETENTION", "success_delete_failure_keep"
        ),
        kill_residual_browser=_read_bool("WEB_LLM_KILL_RESIDUAL_BROWSER", False),
        doubao_input_selector=os.getenv(
            "WEB_LLM_DOUBAO_INPUT_SELECTOR", "textarea, div[contenteditable='true']"
        ),
        doubao_send_selector=os.getenv(
            "WEB_LLM_DOUBAO_SEND_SELECTOR",
            "button[data-testid='send-button'], button[type='submit'], button[aria-label='\\u53d1\\u9001'], button[aria-label='Send']",
        ),
        doubao_response_selector=os.getenv(
            "WEB_LLM_DOUBAO_RESPONSE_SELECTOR",
            "[data-testid='message-content'], .message-content, .answer-content",
        ),
    )


settings = load_settings()
