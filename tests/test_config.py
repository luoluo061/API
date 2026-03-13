from __future__ import annotations

import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from web_adapter.config import PROJECT_ROOT, Settings, load_settings
from web_adapter.service import create_app


class ConfigTests(unittest.TestCase):
    def test_default_paths_are_resolved_from_project_root(self) -> None:
        settings = load_settings(environ={}, project_root=PROJECT_ROOT)

        self.assertEqual(settings.master_profile_dir, (PROJECT_ROOT / ".profiles/masters/doubao-edge").resolve())
        self.assertEqual(settings.runtime_profile_root, (PROJECT_ROOT / ".profiles/runtime/doubao-edge").resolve())
        self.assertEqual(settings.artifact_dir, (PROJECT_ROOT / ".artifacts").resolve())

    def test_new_environment_variables_override_defaults(self) -> None:
        settings = load_settings(
            environ={
                "MASTER_PROFILE_DIR": "custom/master",
                "RUNTIME_PROFILE_DIR": "custom/runtime",
                "ARTIFACT_DIR": "custom/artifacts",
                "HOST": "0.0.0.0",
                "PORT": "9000",
                "BROWSER_MODE": "cdp",
                "CDP_URL": "http://127.0.0.1:9333",
            },
            project_root=PROJECT_ROOT,
        )

        self.assertEqual(settings.master_profile_dir, (PROJECT_ROOT / "custom/master").resolve())
        self.assertEqual(settings.runtime_profile_root, (PROJECT_ROOT / "custom/runtime").resolve())
        self.assertEqual(settings.artifact_dir, (PROJECT_ROOT / "custom/artifacts").resolve())
        self.assertEqual(settings.host, "0.0.0.0")
        self.assertEqual(settings.port, 9000)
        self.assertEqual(settings.cdp_url, "http://127.0.0.1:9333")

    def test_new_environment_variables_take_precedence_over_legacy(self) -> None:
        settings = load_settings(
            environ={
                "MASTER_PROFILE_DIR": "new/master",
                "WEB_LLM_MASTER_PROFILE_DIR": "legacy/master",
            },
            project_root=PROJECT_ROOT,
        )

        self.assertEqual(settings.master_profile_dir, (PROJECT_ROOT / "new/master").resolve())

    def test_legacy_environment_variables_still_work(self) -> None:
        settings = load_settings(
            environ={
                "WEB_LLM_MASTER_PROFILE_DIR": "legacy/master",
                "WEB_LLM_RUNTIME_PROFILE_ROOT": "legacy/runtime",
                "WEB_LLM_HOST": "127.0.0.2",
                "WEB_LLM_PORT": "8100",
            },
            project_root=PROJECT_ROOT,
        )

        self.assertEqual(settings.master_profile_dir, (PROJECT_ROOT / "legacy/master").resolve())
        self.assertEqual(settings.runtime_profile_root, (PROJECT_ROOT / "legacy/runtime").resolve())
        self.assertEqual(settings.host, "127.0.0.2")
        self.assertEqual(settings.port, 8100)

    def test_absolute_paths_are_preserved(self) -> None:
        absolute = Path("C:/temp/doubao-master")
        settings = load_settings(
            environ={"MASTER_PROFILE_DIR": str(absolute)},
            project_root=PROJECT_ROOT,
        )

        self.assertEqual(settings.master_profile_dir, absolute.resolve())

    def test_dotenv_is_loaded_without_overriding_process_env(self) -> None:
        tmp_root = Path("tmp_test_config_env").resolve()
        tmp_root.mkdir(parents=True, exist_ok=True)
        dotenv_path = tmp_root / ".env"
        dotenv_path.write_text(
            "\n".join(
                [
                    "HOST=0.0.0.0",
                    "PORT=8123",
                    "MASTER_PROFILE_DIR=dotenv/master",
                ]
            ),
            encoding="utf-8",
        )

        settings = load_settings(
            environ={"PORT": "9001"},
            dotenv_path=dotenv_path,
            project_root=tmp_root,
        )

        self.assertEqual(settings.host, "0.0.0.0")
        self.assertEqual(settings.port, 9001)
        self.assertEqual(settings.master_profile_dir, (tmp_root / "dotenv/master").resolve())

    def test_startup_logs_resolved_configuration(self) -> None:
        tmp_root = Path("tmp_test_config_logging").resolve()
        settings = Settings(
            project_root=tmp_root,
            artifact_dir=tmp_root / "artifacts",
            master_profile_dir=tmp_root / "master",
            runtime_profile_root=tmp_root / "runtime",
            mock_mode=True,
            browser_mode="cdp",
            cdp_url="http://127.0.0.1:9222",
        )
        app = create_app(settings)

        with self.assertLogs("web_adapter", level="INFO") as captured:
            with TestClient(app) as client:
                response = client.get("/health")

        self.assertEqual(response.status_code, 200)
        combined = "\n".join(captured.output)
        self.assertIn("startup_configuration", combined)
        self.assertIn('"master_profile_dir"', combined)
        self.assertIn('"runtime_profile_root"', combined)
        self.assertIn(tmp_root.name, combined)


if __name__ == "__main__":
    unittest.main()
