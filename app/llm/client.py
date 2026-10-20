from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any
from urllib import error, request

from pydantic import BaseModel, Field, ValidationError


@dataclass(frozen=True)
class LLMSettings:
    api_key: str | None
    base_url: str
    model: str
    timeout_seconds: int


class _LLMMessagePayload(BaseModel):
    content: str


class _LLMChoicePayload(BaseModel):
    message: _LLMMessagePayload


class _LLMChatCompletionPayload(BaseModel):
    choices: list[_LLMChoicePayload] = Field(min_length=1)


def load_llm_settings() -> LLMSettings:
    api_key = os.getenv("LEGAL_LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("LEGAL_LLM_BASE_URL") or os.getenv("OPENAI_BASE_URL") or "https://api.openai.com/v1"
    model = os.getenv("LEGAL_LLM_MODEL") or os.getenv("OPENAI_MODEL") or "gpt-4o-mini"
    timeout_seconds = int(os.getenv("LEGAL_LLM_TIMEOUT_SECONDS", "30"))
    if timeout_seconds <= 0:
        raise ValueError("LEGAL_LLM_TIMEOUT_SECONDS must be positive")
    return LLMSettings(api_key=api_key, base_url=base_url, model=model, timeout_seconds=timeout_seconds)


def request_json_completion(settings: LLMSettings, system_prompt: str, user_prompt: str) -> tuple[dict[str, Any], str]:
    """Call an OpenAI-compatible chat completion endpoint in JSON mode.

    Returns the parsed JSON object from the first choice plus the raw message content.
    Raises RuntimeError with a stable reason code on network, JSON, or schema failures.
    """
    payload = {
        "model": settings.model,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    api_request = request.Request(
        url=settings.base_url.rstrip("/") + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {settings.api_key}",
        },
    )

    try:
        with request.urlopen(api_request, timeout=settings.timeout_seconds) as response:
            raw = response.read().decode("utf-8")
    except TimeoutError as exc:  # pragma: no cover - depends on external network
        raise RuntimeError("api_timeout") from exc
    except error.URLError as exc:  # pragma: no cover - depends on external network
        raise RuntimeError("api_error") from exc

    data = parse_json_object(raw, "chat_completion_response")
    try:
        completion = _LLMChatCompletionPayload.model_validate(data)
    except ValidationError as exc:
        raise RuntimeError("chat_completion_schema_validation_failure") from exc

    message = completion.choices[0].message.content
    return parse_json_object(message, "llm_content"), message


def parse_json_object(raw: str, label: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"malformed_{label}_json") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError(f"{label}_json_must_be_object")
    return parsed


def fallback_reason(code: str, exc: Exception) -> str:
    cause = exc.__cause__ or exc
    message = str(cause).strip() or cause.__class__.__name__
    return f"{code}: {exc}: {cause.__class__.__name__}: {message}"[:240]
