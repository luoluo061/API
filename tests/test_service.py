from __future__ import annotations

import asyncio
import shutil
import unittest
from pathlib import Path

from pydantic import ValidationError

from web_adapter.config import Settings
from web_adapter.models import ChatRequest, ProfileVerifyRequest
from web_adapter.service import AdapterService


def clean(path: Path) -> None:
    shutil.rmtree(path, ignore_errors=True)


def build_settings(tmp_path: Path) -> Settings:
    return Settings(
        mock_mode=True,
        artifact_dir=tmp_path / "artifacts",
        master_profile_dir=tmp_path / "master",
        runtime_profile_root=tmp_path / "runtime",
        browser_mode="cdp",
        cdp_url="http://127.0.0.1:9222",
        profile_mode="dedicated",
    )


class AdapterServiceTests(unittest.TestCase):
    def tearDown(self) -> None:
        clean(Path("tmp_test_health"))
        clean(Path("tmp_test_chat"))
        clean(Path("tmp_test_verify"))
        clean(Path("tmp_test_missing_master"))

    def test_health_reports_mock_mode(self) -> None:
        tmp_path = Path("tmp_test_health")
        service = AdapterService(build_settings(tmp_path))

        response = asyncio.run(service.health())

        self.assertEqual(response.browser.status, "ok")
        self.assertEqual(response.master_profile.status, "ok")
        self.assertTrue(response.mock_mode)
        self.assertEqual(response.provider.detail, "mock provider ready")

    def test_chat_returns_mock_response(self) -> None:
        tmp_path = Path("tmp_test_chat")
        service = AdapterService(build_settings(tmp_path))

        response = asyncio.run(service.chat(ChatRequest(provider="doubao", prompt="hello")))

        self.assertEqual(response.status, "ok")
        self.assertEqual(response.provider, "doubao")
        self.assertTrue(response.content_markdown.startswith("[mock:doubao]"))
        self.assertEqual(response.content, response.content_markdown)
        self.assertEqual(response.blocks, [])
        self.assertEqual(response.diagnostics.browser_mode, "cdp")

    def test_verify_profile_returns_logged_in_in_mock_mode(self) -> None:
        tmp_path = Path("tmp_test_verify")
        service = AdapterService(build_settings(tmp_path))

        response = asyncio.run(service.verify_profile(ProfileVerifyRequest(provider="doubao")))

        self.assertEqual(response.status, "ok")
        self.assertEqual(response.login_state, "logged_in")
        self.assertEqual(response.diagnostics.browser_mode, "cdp")
        self.assertTrue(response.diagnostics.page_ready)

    def test_missing_master_profile_is_reported(self) -> None:
        tmp_path = Path("tmp_test_missing_master")
        settings = Settings(
            mock_mode=False,
            artifact_dir=tmp_path / "artifacts",
            master_profile_dir=tmp_path / "missing-master",
            runtime_profile_root=tmp_path / "runtime",
            browser_mode="launch",
            profile_mode="dedicated",
        )
        service = AdapterService(settings)

        response = asyncio.run(service.verify_profile(ProfileVerifyRequest(provider="doubao")))

        self.assertEqual(response.status, "error")
        self.assertEqual(response.error.code, "master_profile_missing")

    def test_request_validation_rejects_unknown_provider(self) -> None:
        with self.assertRaises(ValidationError):
            ChatRequest(provider="unknown", prompt="hello")  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
