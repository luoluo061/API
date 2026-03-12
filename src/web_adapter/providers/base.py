from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from web_adapter.browser import BrowserSession
from web_adapter.diagnostics import ArtifactSet


@dataclass(slots=True)
class ProviderContext:
    request_id: str
    timeout_seconds: int
    session_id: str | None
    metadata: dict[str, Any]
    browser: BrowserSession
    artifacts: ArtifactSet
    runtime_profile_path: str | None = None


@dataclass(slots=True)
class ProviderResult:
    content: str = ""
    usage_like_meta: dict[str, Any] = field(default_factory=dict)
    page_url: str | None = None


class ProviderAdapter(Protocol):
    name: str

    async def prepare(self, context: ProviderContext) -> None: ...

    async def send_prompt(self, context: ProviderContext, prompt: str) -> None: ...

    async def wait_response(self, context: ProviderContext) -> None: ...

    async def extract_result(self, context: ProviderContext) -> ProviderResult: ...

    async def recover(self, context: ProviderContext, failure: Exception) -> None: ...

    async def healthcheck(self, browser: BrowserSession) -> tuple[str, str]: ...
