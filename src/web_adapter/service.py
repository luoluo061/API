from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from web_adapter.browser import BrowserManager, BrowserSession
from web_adapter.config import Settings, settings
from web_adapter.diagnostics import DiagnosticStore
from web_adapter.errors import AdapterError
from web_adapter.logging_utils import append_request_log, configure_logging
from web_adapter.models import (
    ArtifactPayload,
    ChatRequest,
    ChatResponse,
    DiagnosticsPayload,
    ErrorPayload,
    HealthComponent,
    HealthResponse,
    ProfileVerifyRequest,
    ProfileVerifyResponse,
)
from web_adapter.providers import DoubaoProvider
from web_adapter.providers.base import ProviderContext


class AdapterService:
    def __init__(self, settings_obj: Settings) -> None:
        self.settings = settings_obj
        self.browser = BrowserManager(settings_obj)
        self.diagnostics = DiagnosticStore(settings_obj.artifact_dir)
        self.providers = {"doubao": DoubaoProvider(settings_obj)}
        self.queue_depth = 0

    async def verify_profile(self, request: ProfileVerifyRequest) -> ProfileVerifyResponse:
        request_id = uuid4().hex
        provider = self.providers[request.provider]
        artifacts = self.diagnostics.create(request_id)
        timeout_seconds = request.timeout_seconds or min(self.settings.request_timeout_seconds, 30)
        context: ProviderContext | None = None
        session: BrowserSession | None = None
        success = False

        append_request_log(artifacts.request_log_path, "profile_verify_started", request_id=request_id, provider=request.provider)

        try:
            async with self._acquire_execution_slot(request_id):
                runtime_profile = await self.browser.prepare_runtime_profile(request_id)
                session = await self.browser.open_session(runtime_profile)
                context = ProviderContext(
                    request_id=request_id,
                    timeout_seconds=timeout_seconds,
                    session_id=None,
                    metadata={},
                    browser=session,
                    artifacts=artifacts,
                    runtime_profile_path=str(runtime_profile),
                )
                if self.settings.trace_mode in {"failure", "always"} and session.context is not None:
                    await session.context.tracing.start(screenshots=True, snapshots=True)
                await provider.prepare(context)
                success = True
                if self.settings.trace_mode == "always" and session.context is not None:
                    await session.context.tracing.stop(path=str(artifacts.trace_path))

                append_request_log(artifacts.request_log_path, "profile_verify_finished", request_id=request_id, provider=request.provider, status="ok")
                return ProfileVerifyResponse(
                    request_id=request_id,
                    provider=request.provider,
                    status="ok",
                    login_state="logged_in",
                    artifacts=self._artifact_payload(artifacts, session.runtime_profile_path, page_url=session.page.url if session.page else None),
                    diagnostics=DiagnosticsPayload(
                        browser_mode=self.settings.browser_mode,
                        login_state_source="provider_prepare",
                        page_ready=True,
                    ),
                )
        except AdapterError as exc:
            if context is not None:
                await self._capture_failure(context, exc)
            append_request_log(
                artifacts.request_log_path,
                "profile_verify_finished",
                request_id=request_id,
                provider=request.provider,
                status="error",
                error_code=exc.definition.code,
                detail=exc.detail,
            )
            return ProfileVerifyResponse(
                request_id=request_id,
                provider=request.provider,
                status="error",
                login_state="login_required" if exc.error_key == "login_required" else "unknown",
                artifacts=self._artifact_payload(
                    artifacts,
                    session.runtime_profile_path if session is not None else None,
                    page_url=session.page.url if session is not None and session.page is not None else None,
                ),
                diagnostics=DiagnosticsPayload(
                    browser_mode=self.settings.browser_mode,
                    login_state_source="login_indicator" if exc.error_key == "login_required" else "provider_prepare",
                    page_ready=False if exc.error_key == "page_not_ready" else None,
                ),
                error=self._error_payload(exc),
            )
        finally:
            if session is not None:
                await self.browser.close_session(session)
                self.browser.finalize_runtime_profile(session.runtime_profile_path, success=success)

    async def chat(self, request: ChatRequest) -> ChatResponse:
        request_id = uuid4().hex
        provider = self.providers.get(request.provider)
        if provider is None:
            raise AdapterError("provider_not_supported", detail=request.provider)

        timeout_seconds = request.timeout_seconds or self.settings.request_timeout_seconds
        artifacts = self.diagnostics.create(request_id)
        context: ProviderContext | None = None
        session: BrowserSession | None = None
        success = False

        append_request_log(artifacts.request_log_path, "chat_request_started", request_id=request_id, provider=request.provider)

        try:
            async with self._acquire_execution_slot(request_id):
                runtime_profile = await self.browser.prepare_runtime_profile(request_id)
                session = await self.browser.open_session(runtime_profile)
                context = ProviderContext(
                    request_id=request_id,
                    timeout_seconds=timeout_seconds,
                    session_id=request.session_id,
                    metadata=request.metadata,
                    browser=session,
                    artifacts=artifacts,
                    runtime_profile_path=str(runtime_profile),
                )
                if self.settings.trace_mode in {"failure", "always"} and session.context is not None:
                    await session.context.tracing.start(screenshots=True, snapshots=True)

                await provider.prepare(context)
                await provider.send_prompt(context, request.prompt)
                await provider.wait_response(context)
                result = await provider.extract_result(context)
                success = True

                if self.settings.trace_mode == "always" and session.context is not None:
                    await session.context.tracing.stop(path=str(artifacts.trace_path))

                append_request_log(artifacts.request_log_path, "chat_request_finished", request_id=request_id, provider=request.provider, status="ok")
                blocks = list(result.usage_like_meta.get("blocks", []))
                content_markdown = result.content
                diagnostics = DiagnosticsPayload(
                    extraction_path=result.usage_like_meta.get("extraction_path"),
                    content_format=result.usage_like_meta.get("content_format"),
                    completion_signals=result.usage_like_meta.get("completion_signals", {}),
                    response_length=result.usage_like_meta.get("response_length"),
                    fallback_used=result.usage_like_meta.get("extraction_path") in {"copy_fallback", "settled_text_fallback", "plain_text_fallback"},
                    browser_mode=self.settings.browser_mode,
                )
                return ChatResponse(
                    request_id=request_id,
                    provider=request.provider,
                    status="ok",
                    content_markdown=content_markdown,
                    blocks=blocks,
                    usage_like_meta=result.usage_like_meta,
                    artifacts=self._artifact_payload(artifacts, session.runtime_profile_path, page_url=result.page_url),
                    diagnostics=diagnostics,
                    content=content_markdown,
                )
        except AdapterError as exc:
            if context is not None:
                await self._capture_failure(context, exc)
            append_request_log(
                artifacts.request_log_path,
                "chat_request_finished",
                request_id=request_id,
                provider=request.provider,
                status="error",
                error_code=exc.definition.code,
                detail=exc.detail,
            )
            return ChatResponse(
                request_id=request_id,
                provider=request.provider,
                status="error",
                content_markdown=None,
                blocks=[],
                artifacts=self._artifact_payload(
                    artifacts,
                    session.runtime_profile_path if session is not None else None,
                    page_url=session.page.url if session is not None and session.page is not None else None,
                ),
                diagnostics=DiagnosticsPayload(browser_mode=self.settings.browser_mode),
                content=None,
                error=self._error_payload(exc),
            )
        finally:
            if session is not None:
                await self.browser.close_session(session)
                self.browser.finalize_runtime_profile(session.runtime_profile_path, success=success)

    async def _capture_failure(self, context: ProviderContext, exc: AdapterError) -> None:
        provider = self.providers["doubao"]
        await provider.recover(context, exc)
        if (
            self.settings.trace_mode in {"failure", "always"}
            and not self.settings.mock_mode
            and context.browser.context is not None
        ):
            try:
                await context.browser.context.tracing.stop(path=str(context.artifacts.trace_path))
            except Exception:
                pass

    @asynccontextmanager
    async def _acquire_execution_slot(self, request_id: str):
        self.queue_depth += 1
        try:
            await asyncio.wait_for(self.browser.lock.acquire(), timeout=self.settings.queue_wait_seconds)
        except TimeoutError as exc:
            raise AdapterError("queue_timeout", detail=f"request_id={request_id}") from exc
        finally:
            self.queue_depth -= 1

        try:
            yield
        finally:
            self.browser.lock.release()

    async def health(self) -> HealthResponse:
        browser_status, browser_detail = await self.browser.healthcheck()
        master_status, master_detail = self.browser.inspect_master_profile()

        provider_status = "warn"
        provider_detail = "use /profiles/verify to validate CDP login state and page readiness"
        if self.settings.mock_mode:
            provider_status = "ok"
            provider_detail = "mock provider ready"
        elif browser_status != "ok":
            provider_detail = "CDP unavailable; verify browser startup and /json/version"

        runtime_status = "warn"
        runtime_detail = f"{self.settings.runtime_profile_root} (unused in default CDP mode)"
        self.settings.runtime_profile_root.mkdir(parents=True, exist_ok=True)

        master_detail = f"{master_detail} (compatibility field; CDP mode does not require launch-time profile reuse)"

        return HealthResponse(
            service=HealthComponent(status="ok", detail=self.settings.app_name),
            browser=HealthComponent(status=browser_status, detail=browser_detail),
            master_profile=HealthComponent(status=master_status, detail=master_detail),
            runtime_profile_root=HealthComponent(status=runtime_status, detail=runtime_detail),
            provider=HealthComponent(status=provider_status, detail=provider_detail),
            queue_depth=self.queue_depth,
            browser_channel=self.settings.browser_channel,
            mock_mode=self.settings.mock_mode,
        )

    def _artifact_payload(self, artifacts, runtime_profile_path, page_url: str | None) -> ArtifactPayload:
        return ArtifactPayload(
            screenshot_path=str(artifacts.screenshot_path) if artifacts.screenshot_path.exists() else None,
            html_snapshot_path=str(artifacts.html_snapshot_path) if artifacts.html_snapshot_path.exists() else None,
            trace_path=str(artifacts.trace_path) if artifacts.trace_path.exists() else None,
            request_log_path=str(artifacts.request_log_path),
            runtime_profile_path=str(runtime_profile_path) if runtime_profile_path else None,
            page_url=page_url,
            retry_count=0,
        )

    def _error_payload(self, exc: AdapterError) -> ErrorPayload:
        return ErrorPayload(
            code=exc.definition.code,
            message=exc.definition.message,
            retryable=exc.definition.retryable,
            detail=exc.detail,
        )


def create_app(settings_obj: Settings = settings) -> FastAPI:
    configure_logging()
    service = AdapterService(settings_obj)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        settings_obj.artifact_dir.mkdir(parents=True, exist_ok=True)
        settings_obj.runtime_profile_root.mkdir(parents=True, exist_ok=True)
        if settings_obj.startup_browser_check:
            await service.browser.startup()
        yield
        await service.browser.shutdown()

    app = FastAPI(title=settings_obj.app_name, lifespan=lifespan)
    app.state.service = service

    @app.post("/profiles/verify", response_model=ProfileVerifyResponse)
    async def verify_profile_endpoint(request: ProfileVerifyRequest) -> ProfileVerifyResponse:
        return await service.verify_profile(request)

    @app.post("/chat", response_model=ChatResponse)
    async def chat_endpoint(request: ChatRequest) -> ChatResponse:
        return await service.chat(request)

    @app.get("/health", response_model=HealthResponse)
    async def health_endpoint() -> HealthResponse:
        return await service.health()

    @app.exception_handler(AdapterError)
    async def adapter_error_handler(_, exc: AdapterError) -> JSONResponse:
        payload = ErrorPayload(
            code=exc.definition.code,
            message=exc.definition.message,
            retryable=exc.definition.retryable,
            detail=exc.detail,
        )
        return JSONResponse(status_code=400, content={"error": payload.model_dump()})

    @app.get("/")
    async def root() -> dict[str, str]:
        return {"service": settings_obj.app_name, "status": "ok"}

    return app
