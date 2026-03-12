from __future__ import annotations

import asyncio
import shutil
from dataclasses import dataclass
from pathlib import Path

from web_adapter.config import Settings
from web_adapter.errors import AdapterError


try:
    from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright
except ImportError:  # pragma: no cover - handled at runtime
    Browser = BrowserContext = Page = Playwright = object  # type: ignore[assignment]
    async_playwright = None


LOCK_FILES = ("SingletonLock", "SingletonCookie", "SingletonSocket", "lockfile")


@dataclass(slots=True)
class BrowserSession:
    browser: Browser | None
    context: BrowserContext | None
    page: Page | None
    runtime_profile_path: Path | None
    owns_page: bool = False
    attached_via_cdp: bool = False


class BrowserManager:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._playwright: Playwright | None = None
        self._lock = asyncio.Lock()

    async def startup(self) -> None:
        if self._settings.mock_mode:
            return
        if async_playwright is None:
            raise AdapterError("browser_unavailable", detail="playwright is not installed")
        if self._playwright is None:
            self._playwright = await async_playwright().start()

    async def shutdown(self) -> None:
        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None

    def inspect_master_profile(self) -> tuple[str, str]:
        if self._settings.mock_mode:
            return "ok", "mock mode enabled"
        master = self._settings.master_profile_dir
        if not master.exists() or not any(master.iterdir()):
            status = "warn" if self._settings.browser_mode == "cdp" else "error"
            detail = f"master profile missing or empty: {master}"
            if self._settings.browser_mode == "cdp":
                detail = f"{detail}; CDP mode can still work if Edge was started manually with another profile"
            return status, detail
        lock_paths = [str(master / name) for name in LOCK_FILES if (master / name).exists()]
        if lock_paths and self._settings.browser_mode != "cdp":
            return "warn", f"master profile appears locked: {', '.join(lock_paths)}"
        if self._settings.browser_mode == "cdp":
            return "ok", f"{master}; expected manual Edge user-data-dir for CDP"
        return "ok", f"{master}; browser_mode={self._settings.browser_mode}"

    async def prepare_runtime_profile(self, request_id: str) -> Path:
        if self._settings.mock_mode:
            runtime = self._settings.runtime_profile_root / request_id
            runtime.mkdir(parents=True, exist_ok=True)
            return runtime

        master = self._settings.master_profile_dir
        if not master.exists() or not any(master.iterdir()):
            raise AdapterError("master_profile_missing", detail=str(master))

        if self._settings.browser_mode == "cdp":
            return master

        lock_paths = [str(master / name) for name in LOCK_FILES if (master / name).exists()]
        if lock_paths:
            raise AdapterError("profile_locked", detail=f"master profile locked: {', '.join(lock_paths)}")

        if self._settings.profile_mode == "dedicated":
            return master

        runtime_root = self._settings.runtime_profile_root
        runtime_root.mkdir(parents=True, exist_ok=True)
        runtime_dir = runtime_root / request_id
        if runtime_dir.exists():
            shutil.rmtree(runtime_dir, ignore_errors=True)

        try:
            shutil.copytree(master, runtime_dir)
        except Exception as exc:
            raise AdapterError("runtime_profile_copy_failed", detail=str(exc)) from exc
        return runtime_dir

    async def open_session(self, runtime_profile_path: Path) -> BrowserSession:
        if self._settings.mock_mode:
            return BrowserSession(browser=None, context=None, page=None, runtime_profile_path=runtime_profile_path)

        await self.startup()
        assert self._playwright is not None

        if self._settings.browser_mode == "cdp":
            return await self._open_cdp_session(runtime_profile_path)
        return await self._open_launch_session(runtime_profile_path)

    async def _open_launch_session(self, runtime_profile_path: Path) -> BrowserSession:
        assert self._playwright is not None
        try:
            context = await self._playwright.chromium.launch_persistent_context(
                user_data_dir=str(runtime_profile_path),
                channel=self._settings.browser_channel,
                headless=self._settings.headless,
            )
        except Exception as exc:  # pragma: no cover - browser-specific
            detail = str(exc)
            if "lock" in detail.lower() or "used by another process" in detail.lower():
                raise AdapterError("profile_locked", detail=detail) from exc
            raise AdapterError("browser_unavailable", detail=detail) from exc

        page = context.pages[0] if context.pages else await context.new_page()
        return BrowserSession(browser=None, context=context, page=page, runtime_profile_path=runtime_profile_path)

    async def _open_cdp_session(self, runtime_profile_path: Path) -> BrowserSession:
        assert self._playwright is not None
        try:
            browser = await self._playwright.chromium.connect_over_cdp(self._settings.cdp_url)
        except Exception as exc:
            raise AdapterError("cdp_unreachable", detail=f"{self._settings.cdp_url}: {exc}") from exc

        contexts = browser.contexts
        if not contexts:
            await browser.close()
            raise AdapterError("cdp_unreachable", detail="cdp browser has no contexts")
        context = contexts[0]
        page = await context.new_page()
        return BrowserSession(
            browser=browser,
            context=context,
            page=page,
            runtime_profile_path=runtime_profile_path,
            owns_page=True,
            attached_via_cdp=True,
        )

    async def close_session(self, session: BrowserSession) -> None:
        if session.attached_via_cdp:
            if session.owns_page and session.page is not None:
                await session.page.close()
            return
        if session.context is not None:
            await session.context.close()

    def finalize_runtime_profile(self, runtime_profile_path: Path | None, success: bool) -> None:
        if runtime_profile_path is None:
            return
        if self._settings.browser_mode == "cdp":
            return
        if self._settings.profile_mode == "dedicated":
            return
        retention = self._settings.runtime_profile_retention
        should_keep = retention == "keep_all" or (retention == "success_delete_failure_keep" and not success)
        if should_keep:
            return
        shutil.rmtree(runtime_profile_path, ignore_errors=True)

    async def healthcheck(self) -> tuple[str, str]:
        if self._settings.mock_mode:
            return "ok", "mock mode enabled"
        try:
            await self.startup()
            if self._settings.browser_mode == "cdp":
                assert self._playwright is not None
                browser = await self._playwright.chromium.connect_over_cdp(self._settings.cdp_url)
                try:
                    if not browser.contexts:
                        return "error", f"cdp reachable but no browser contexts: {self._settings.cdp_url}"
                    return "ok", f"cdp ready: {self._settings.cdp_url}"
                finally:
                    await browser.close()
            return "ok", "playwright ready"
        except AdapterError as exc:
            return "error", exc.detail or exc.definition.message
        except Exception as exc:
            return "error", str(exc)

    @property
    def lock(self) -> asyncio.Lock:
        return self._lock
