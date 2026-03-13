from __future__ import annotations

import json
import unittest
from pathlib import Path
from time import time

from fastapi.testclient import TestClient

from web_adapter.config import Settings
from web_adapter.models import ErrorPayload
from web_adapter.openai_compat import (
    OPENAI_MODEL_ID,
    build_streaming_chunks,
    current_timestamp,
    map_error_to_openai,
    map_openai_request_to_chat_request,
)
from web_adapter.service import create_app


def build_settings(tmp_path: Path, *, mock_mode: bool = True) -> Settings:
    return Settings(
        mock_mode=mock_mode,
        artifact_dir=tmp_path / "artifacts",
        master_profile_dir=tmp_path / "master",
        runtime_profile_root=tmp_path / "runtime",
        browser_mode="cdp" if mock_mode else "launch",
        cdp_url="http://127.0.0.1:9222",
        profile_mode="dedicated",
    )


def read_matching_request_log(tmp_path: Path, needle: str) -> str:
    for path in sorted((tmp_path / "artifacts").glob("*/request.log"), reverse=True):
        content = path.read_text(encoding="utf-8")
        if needle in content:
            return content
    raise AssertionError(f"request log containing {needle!r} not found")


class OpenAICompatTests(unittest.TestCase):
    def test_models_endpoint_returns_single_doubao_web_model(self) -> None:
        app = create_app(build_settings(Path("tmp_test_openai_models")))
        client = TestClient(app)

        response = client.get("/v1/models")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["object"], "list")
        self.assertEqual(payload["data"], [{"id": OPENAI_MODEL_ID, "object": "model", "created": 0, "owned_by": "web-llm-adapter"}])

    def test_chat_completions_endpoint_reuses_chat_service(self) -> None:
        tmp_path = Path("tmp_test_openai_chat")
        app = create_app(build_settings(tmp_path))
        client = TestClient(app)

        before = int(time())
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": OPENAI_MODEL_ID,
                "messages": [{"role": "user", "content": "hello"}],
                "temperature": 0.2,
                "unknown_field": "ignored",
            },
        )
        after = int(time())

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["object"], "chat.completion")
        self.assertEqual(payload["model"], OPENAI_MODEL_ID)
        self.assertEqual(payload["choices"][0]["message"]["role"], "assistant")
        self.assertTrue(payload["choices"][0]["message"]["content"].startswith("[mock:doubao]"))
        self.assertEqual(payload["usage"], {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0})
        self.assertGreaterEqual(payload["created"], before)
        self.assertLessEqual(payload["created"], after)

        request_log = read_matching_request_log(tmp_path, "openai_chat_completions_started")
        self.assertIn("openai_chat_completions_started", request_log)
        self.assertIn("openai_chat_completions_finished", request_log)
        self.assertIn("\\\"unknown_field\\\":\\\"ignored\\\"", request_log)
        self.assertIn("\"content_type\": \"application/json\"", request_log)
        self.assertIn("\"status_code\": 200", request_log)

    def test_messages_are_flattened_into_prompt_for_multi_turn_requests(self) -> None:
        request, meta = map_openai_request_to_chat_request(
            {
                "model": OPENAI_MODEL_ID,
                "messages": [
                    {"role": "system", "content": "You are concise."},
                    {"role": "user", "content": "Summarize this."},
                    {"role": "assistant", "content": "Sure."},
                    {"role": "user", "content": "Now shorten it."},
                ],
            }
        )

        self.assertEqual(
            request.prompt,
            "System: You are concise.\n\nUser: Summarize this.\n\nAssistant: Sure.\n\nUser: Now shorten it.",
        )
        self.assertEqual(meta["normalized_messages"][0]["content"], "You are concise.")

    def test_chat_completions_rejects_unknown_model(self) -> None:
        app = create_app(build_settings(Path("tmp_test_openai_bad_model")))
        client = TestClient(app)

        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "gpt-4o",
                "messages": [{"role": "user", "content": "hello"}],
            },
        )

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertEqual(payload["error"]["type"], "invalid_request_error")
        self.assertEqual(payload["error"]["code"], "unsupported_model")

    def test_chat_completions_streams_sse_when_requested(self) -> None:
        tmp_path = Path("tmp_test_openai_stream")
        app = create_app(build_settings(tmp_path))
        client = TestClient(app)

        with client.stream(
            "POST",
            "/v1/chat/completions",
            json={
                "model": OPENAI_MODEL_ID,
                "stream": True,
                "messages": [{"role": "user", "content": "hello"}],
            },
        ) as response:
            body = "".join(chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk for chunk in response.iter_text())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "text/event-stream; charset=utf-8")
        self.assertEqual(response.headers["cache-control"], "no-cache")
        self.assertEqual(response.headers["connection"], "keep-alive")
        self.assertIn("\"object\": \"chat.completion.chunk\"", body)
        self.assertIn("\"delta\": {\"role\": \"assistant\"}", body)
        self.assertIn("\"delta\": {\"content\": \"", body)
        self.assertIn("\"delta\": {}", body)
        self.assertIn("\"finish_reason\": \"stop\"", body)
        self.assertTrue(body.endswith("data: [DONE]\n\n"))
        self.assertIn("\n\ndata: ", body)

        request_log = read_matching_request_log(tmp_path, "openai_chat_completions_finished")
        self.assertIn("\"stream\": true", request_log)
        self.assertIn("\"content_type\": \"text/event-stream; charset=utf-8\"", request_log)
        self.assertIn("data: [DONE]\\n\\n", request_log)

    def test_chat_completions_accepts_array_text_content(self) -> None:
        request, meta = map_openai_request_to_chat_request(
            {
                "model": OPENAI_MODEL_ID,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "hello"},
                            {"type": "image_url", "image_url": {"url": "ignored"}},
                            {"type": "text", "text": "world"},
                        ],
                    }
                ],
            }
        )

        self.assertEqual(request.prompt, "hello\nworld")
        self.assertEqual(meta["normalized_messages"][0]["content"], "hello\nworld")

    def test_chat_completions_ignores_tools(self) -> None:
        app = create_app(build_settings(Path("tmp_test_openai_tools")))
        client = TestClient(app)

        response = client.post(
            "/v1/chat/completions",
            json={
                "model": OPENAI_MODEL_ID,
                "messages": [{"role": "user", "content": "hello"}],
                "tools": [{"type": "function", "function": {"name": "x", "parameters": {}}}],
                "response_format": {"type": "json_schema"},
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["object"], "chat.completion")

    def test_adapter_errors_are_mapped_to_openai_error_shape(self) -> None:
        status_code, error = map_error_to_openai(
            ErrorPayload(code="master_profile_missing", message="Master profile directory is missing.", retryable=False)
        )

        self.assertEqual(status_code, 400)
        self.assertEqual(error.model_dump()["error"]["type"], "invalid_request_error")
        self.assertEqual(error.model_dump()["error"]["code"], "master_profile_missing")

    def test_chat_completions_maps_service_errors_to_openai_shape(self) -> None:
        tmp_path = Path("tmp_test_openai_service_error")
        app = create_app(
            Settings(
                mock_mode=False,
                artifact_dir=tmp_path / "artifacts",
                master_profile_dir=tmp_path / "missing-master",
                runtime_profile_root=tmp_path / "runtime",
                browser_mode="launch",
                profile_mode="dedicated",
            )
        )
        client = TestClient(app)

        response = client.post(
            "/v1/chat/completions",
            json={
                "model": OPENAI_MODEL_ID,
                "messages": [{"role": "user", "content": "hello"}],
            },
        )

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertEqual(payload["error"]["type"], "invalid_request_error")
        self.assertEqual(payload["error"]["code"], "master_profile_missing")

        request_log = read_matching_request_log(tmp_path, "openai_chat_completions_finished")
        self.assertIn("\"content_type\": \"application/json\"", request_log)
        self.assertIn("\"status_code\": 400", request_log)

    def test_build_streaming_chunks_uses_current_timestamp(self) -> None:
        created = current_timestamp()
        response = type("Resp", (), {"request_id": "abc", "content_markdown": "OK"})()

        chunks = build_streaming_chunks(response, created=created)

        self.assertIn(f"\"created\": {created}", chunks[0])
        self.assertIn("\"content\": \"OK\"", chunks[1])
        self.assertTrue(chunks[-1].endswith("[DONE]\n\n"))


if __name__ == "__main__":
    unittest.main()
