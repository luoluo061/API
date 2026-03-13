from __future__ import annotations

import json
from datetime import UTC, datetime
from time import time
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from web_adapter.models import ChatRequest, ChatResponse, ErrorPayload

OPENAI_MODEL_ID = "doubao-web"
OPENAI_OWNER = "web-llm-adapter"


class OpenAICompatError(Exception):
    def __init__(self, status_code: int, message: str, error_type: str, code: str) -> None:
        self.status_code = status_code
        self.payload = OpenAIErrorResponse(
            error=OpenAIErrorBody(message=message, type=error_type, code=code),
        )
        super().__init__(message)


class OpenAIModelPayload(BaseModel):
    id: str
    object: Literal["model"] = "model"
    created: int = 0
    owned_by: str = OPENAI_OWNER


class OpenAIModelsResponse(BaseModel):
    object: Literal["list"] = "list"
    data: list[OpenAIModelPayload]


class OpenAIChatCompletionMessage(BaseModel):
    role: Literal["assistant"] = "assistant"
    content: str


class OpenAIChatCompletionChoice(BaseModel):
    index: int = 0
    message: OpenAIChatCompletionMessage
    finish_reason: Literal["stop"] = "stop"


class OpenAIUsagePayload(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class OpenAIChatCompletionResponse(BaseModel):
    id: str
    object: Literal["chat.completion"] = "chat.completion"
    created: int
    model: str = OPENAI_MODEL_ID
    choices: list[OpenAIChatCompletionChoice]
    usage: OpenAIUsagePayload = Field(default_factory=OpenAIUsagePayload)


class OpenAIErrorBody(BaseModel):
    message: str
    type: str
    code: str


class OpenAIErrorResponse(BaseModel):
    error: OpenAIErrorBody


class OpenAIChatCompletionRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    model: str
    messages: list[dict[str, Any]]
    stream: bool = False
    temperature: float | None = None
    top_p: float | None = None
    max_tokens: int | None = None
    user: str | None = None
    n: int | None = None
    stop: str | list[str] | None = None
    presence_penalty: float | None = None
    frequency_penalty: float | None = None


def build_models_response() -> OpenAIModelsResponse:
    return OpenAIModelsResponse(data=[OpenAIModelPayload(id=OPENAI_MODEL_ID)])


def current_timestamp() -> int:
    return int(time())


def map_openai_request_to_chat_request(payload: dict[str, Any]) -> tuple[ChatRequest, dict[str, Any]]:
    try:
        request = OpenAIChatCompletionRequest.model_validate(payload)
    except ValidationError as exc:
        raise OpenAICompatError(400, str(exc), "invalid_request_error", "unsupported_messages_format") from exc

    if request.model != OPENAI_MODEL_ID:
        raise OpenAICompatError(400, f"Unsupported model '{request.model}'.", "invalid_request_error", "unsupported_model")
    if not request.messages:
        raise OpenAICompatError(400, "messages must contain at least one item.", "invalid_request_error", "unsupported_messages_format")

    normalized_messages: list[dict[str, str]] = []
    user_count = 0

    for raw_message in request.messages:
        role = raw_message.get("role")
        if role not in {"system", "user", "assistant"}:
            raise OpenAICompatError(400, f"Unsupported message role '{role}'.", "invalid_request_error", "unsupported_messages_format")

        content = _normalize_content(raw_message.get("content"))
        if not content:
            raise OpenAICompatError(400, "Message content must include text.", "invalid_request_error", "unsupported_messages_format")

        if role == "user":
            user_count += 1
        normalized_messages.append({"role": role, "content": content})

    if user_count == 0:
        raise OpenAICompatError(400, "messages must include at least one user message.", "invalid_request_error", "unsupported_messages_format")

    prompt = _build_prompt(normalized_messages)
    return ChatRequest(provider="doubao", prompt=prompt), {
        "stream": request.stream,
        "normalized_messages": normalized_messages,
        "prompt": prompt,
        "message_summary": summarize_messages(request.messages),
    }


def map_chat_response_to_openai(response: ChatResponse, *, created: int | None = None) -> OpenAIChatCompletionResponse:
    content = (response.content_markdown or "").strip()
    return OpenAIChatCompletionResponse(
        id=f"chatcmpl_{response.request_id}",
        created=created or current_timestamp(),
        choices=[
            OpenAIChatCompletionChoice(
                message=OpenAIChatCompletionMessage(content=content),
            )
        ],
    )


def build_streaming_chunks(response: ChatResponse, *, created: int | None = None) -> list[str]:
    ts = created or current_timestamp()
    completion_id = f"chatcmpl_{response.request_id}"
    content = (response.content_markdown or "").strip()
    chunks = [
        {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": ts,
            "model": OPENAI_MODEL_ID,
            "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}],
        },
        {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": ts,
            "model": OPENAI_MODEL_ID,
            "choices": [{"index": 0, "delta": {"content": content}, "finish_reason": None}],
        },
        {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": ts,
            "model": OPENAI_MODEL_ID,
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        },
    ]
    lines = [f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n" for chunk in chunks]
    lines.append("data: [DONE]\n\n")
    return lines


def map_error_to_openai(error: ErrorPayload | None) -> tuple[int, OpenAIErrorResponse]:
    if error is None:
        return 500, OpenAIErrorResponse(
            error=OpenAIErrorBody(
                message="Internal server error.",
                type="api_error",
                code="internal_error",
            )
        )

    status_code, error_type = _ERROR_MAPPING.get(error.code, (500, "api_error"))
    return status_code, OpenAIErrorResponse(
        error=OpenAIErrorBody(
            message=error.message,
            type=error_type,
            code=error.code,
        )
    )


def summarize_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summary: list[dict[str, Any]] = []
    for message in messages:
        content = message.get("content")
        content_type = type(content).__name__
        part_types: list[str] = []
        if isinstance(content, list):
            for part in content:
                if isinstance(part, dict):
                    part_types.append(str(part.get("type", "dict")))
                else:
                    part_types.append(type(part).__name__)
        summary.append(
            {
                "role": message.get("role"),
                "content_type": content_type,
                "part_types": part_types,
            }
        )
    return summary


def serialize_response_body(response: OpenAIChatCompletionResponse | OpenAIErrorResponse) -> dict[str, Any]:
    return response.model_dump()


def iso_timestamp() -> str:
    return datetime.now(UTC).isoformat()


def _normalize_content(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, str):
                stripped = part.strip()
                if stripped:
                    parts.append(stripped)
                continue
            if not isinstance(part, dict):
                continue
            if part.get("type") == "text":
                text = str(part.get("text", "")).strip()
                if text:
                    parts.append(text)
        return "\n".join(parts).strip()
    return ""


def _build_prompt(normalized_messages: list[dict[str, str]]) -> str:
    if len(normalized_messages) == 1 and normalized_messages[0]["role"] == "user":
        return normalized_messages[0]["content"]
    prompt_lines = [f"{item['role'].title()}: {item['content']}" for item in normalized_messages]
    return "\n\n".join(prompt_lines)


_ERROR_MAPPING: dict[str, tuple[int, str]] = {
    "provider_not_supported": (400, "invalid_request_error"),
    "master_profile_missing": (400, "invalid_request_error"),
    "login_required": (400, "invalid_request_error"),
    "page_not_ready": (400, "invalid_request_error"),
    "selector_not_found": (400, "invalid_request_error"),
    "extract_empty": (400, "invalid_request_error"),
    "queue_timeout": (408, "timeout_error"),
    "provider_timeout": (408, "timeout_error"),
    "browser_unavailable": (503, "service_unavailable_error"),
    "cdp_unreachable": (503, "service_unavailable_error"),
    "profile_locked": (503, "service_unavailable_error"),
    "runtime_profile_copy_failed": (503, "service_unavailable_error"),
    "page_navigation_failed": (503, "service_unavailable_error"),
    "provider_error": (500, "api_error"),
    "send_failed": (500, "api_error"),
}
