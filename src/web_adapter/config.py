from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping

from pydantic import BaseModel, Field


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseModel):
    app_name: str = "web-llm-adapter"
    project_root: Path = PROJECT_ROOT
    host: str = "127.0.0.1"
    port: int = 8000
    base_url: str = "https://www.doubao.com/chat/"
    master_profile_dir: Path = PROJECT_ROOT / ".profiles/masters/doubao-edge"
    runtime_profile_root: Path = PROJECT_ROOT / ".profiles/runtime/doubao-edge"
    artifact_dir: Path = PROJECT_ROOT / ".artifacts"
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

    def startup_summary(self) -> dict[str, str | int]:
        return {
            "project_root": str(self.project_root),
            "master_profile_dir": str(self.master_profile_dir),
            "runtime_profile_root": str(self.runtime_profile_root),
            "artifact_dir": str(self.artifact_dir),
            "browser_mode": self.browser_mode,
            "cdp_url": self.cdp_url,
            "host": self.host,
            "port": self.port,
        }


def load_settings(
    environ: Mapping[str, str] | None = None,
    *,
    dotenv_path: Path | None = None,
    project_root: Path | None = None,
) -> Settings:
    env = dict(environ or os.environ)
    root = Path(project_root or PROJECT_ROOT).resolve()
    dotenv_values = _load_dotenv(dotenv_path or (root / ".env"))

    return Settings(
        app_name=_env(env, dotenv_values, "APP_NAME", "WEB_LLM_APP_NAME", "web-llm-adapter"),
        project_root=root,
        host=_env(env, dotenv_values, "HOST", "WEB_LLM_HOST", "127.0.0.1"),
        port=int(_env(env, dotenv_values, "PORT", "WEB_LLM_PORT", "8000")),
        base_url=_env(env, dotenv_values, "BASE_URL", "WEB_LLM_BASE_URL", "https://www.doubao.com/chat/"),
        master_profile_dir=_path_env(
            env,
            dotenv_values,
            root,
            "MASTER_PROFILE_DIR",
            "WEB_LLM_MASTER_PROFILE_DIR",
            ".profiles/masters/doubao-edge",
        ),
        runtime_profile_root=_path_env(
            env,
            dotenv_values,
            root,
            "RUNTIME_PROFILE_DIR",
            "WEB_LLM_RUNTIME_PROFILE_ROOT",
            ".profiles/runtime/doubao-edge",
        ),
        artifact_dir=_path_env(
            env,
            dotenv_values,
            root,
            "ARTIFACT_DIR",
            "WEB_LLM_ARTIFACT_DIR",
            ".artifacts",
        ),
        browser_mode=_env(env, dotenv_values, "BROWSER_MODE", "WEB_LLM_BROWSER_MODE", "cdp"),
        browser_channel=_env(env, dotenv_values, "BROWSER_CHANNEL", "WEB_LLM_BROWSER_CHANNEL", "msedge"),
        cdp_url=_env(env, dotenv_values, "CDP_URL", "WEB_LLM_CDP_URL", "http://127.0.0.1:9222"),
        headless=_bool_env(env, dotenv_values, "HEADLESS", "WEB_LLM_HEADLESS", True),
        trace_mode=_env(env, dotenv_values, "TRACE_MODE", "WEB_LLM_TRACE_MODE", "failure"),
        request_timeout_seconds=int(
            _env(env, dotenv_values, "REQUEST_TIMEOUT_SECONDS", "WEB_LLM_REQUEST_TIMEOUT_SECONDS", "90")
        ),
        queue_wait_seconds=int(_env(env, dotenv_values, "QUEUE_WAIT_SECONDS", "WEB_LLM_QUEUE_WAIT_SECONDS", "30")),
        mock_mode=_bool_env(env, dotenv_values, "MOCK_MODE", "WEB_LLM_MOCK_MODE", False),
        startup_browser_check=_bool_env(
            env,
            dotenv_values,
            "STARTUP_BROWSER_CHECK",
            "WEB_LLM_STARTUP_BROWSER_CHECK",
            False,
        ),
        profile_mode=_env(env, dotenv_values, "PROFILE_MODE", "WEB_LLM_PROFILE_MODE", "dedicated"),
        runtime_profile_retention=_env(
            env,
            dotenv_values,
            "RUNTIME_PROFILE_RETENTION",
            "WEB_LLM_RUNTIME_PROFILE_RETENTION",
            "success_delete_failure_keep",
        ),
        kill_residual_browser=_bool_env(
            env,
            dotenv_values,
            "KILL_RESIDUAL_BROWSER",
            "WEB_LLM_KILL_RESIDUAL_BROWSER",
            False,
        ),
        doubao_input_selector=_env(
            env,
            dotenv_values,
            "DOUBAO_INPUT_SELECTOR",
            "WEB_LLM_DOUBAO_INPUT_SELECTOR",
            "textarea, div[contenteditable='true']",
        ),
        doubao_send_selector=_env(
            env,
            dotenv_values,
            "DOUBAO_SEND_SELECTOR",
            "WEB_LLM_DOUBAO_SEND_SELECTOR",
            "button[data-testid='send-button'], button[type='submit'], button[aria-label='\\u53d1\\u9001'], button[aria-label='Send']",
        ),
        doubao_response_selector=_env(
            env,
            dotenv_values,
            "DOUBAO_RESPONSE_SELECTOR",
            "WEB_LLM_DOUBAO_RESPONSE_SELECTOR",
            "[data-testid='message-content'], .message-content, .answer-content",
        ),
    )


def _env(env: Mapping[str, str], dotenv_values: Mapping[str, str], primary: str, legacy: str, default: str) -> str:
    if primary in env:
        return env[primary]
    if legacy in env:
        return env[legacy]
    if primary in dotenv_values:
        return dotenv_values[primary]
    if legacy in dotenv_values:
        return dotenv_values[legacy]
    return default


def _bool_env(
    env: Mapping[str, str],
    dotenv_values: Mapping[str, str],
    primary: str,
    legacy: str,
    default: bool,
) -> bool:
    raw = _env(env, dotenv_values, primary, legacy, "1" if default else "0")
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _path_env(
    env: Mapping[str, str],
    dotenv_values: Mapping[str, str],
    project_root: Path,
    primary: str,
    legacy: str,
    default: str,
) -> Path:
    raw = _env(env, dotenv_values, primary, legacy, default).strip()
    path = Path(raw)
    if path.is_absolute():
        return path.resolve()
    return (project_root / path).resolve()


def _load_dotenv(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            values[key] = value
    return values


settings = load_settings()
