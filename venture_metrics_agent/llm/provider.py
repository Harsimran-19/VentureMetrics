"""LLM provider adapter.

DeepSeek is the first target because it exposes an OpenAI-compatible chat API.
The rest of the code should depend on this adapter, not on a vendor SDK.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class LLMConfig:
    provider: str = "deepseek"
    base_url: str = "https://api.deepseek.com"
    api_key: str | None = None
    model: str = "deepseek-chat"
    reasoning_model: str = "deepseek-reasoner"
    reasoning_effort: str | None = None
    timeout: float = 60.0


class LLMProvider:
    def __init__(self, config: LLMConfig | None = None) -> None:
        self.config = config or load_llm_config()

    @property
    def is_configured(self) -> bool:
        return bool(self.config.api_key)

    def complete_json(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.1,
        reasoning: bool = False,
    ) -> dict[str, Any]:
        if not self.config.api_key:
            raise RuntimeError("LLM_API_KEY is missing. Add it to .env or export it in the shell.")

        endpoint = self.config.base_url.rstrip("/") + "/chat/completions"
        request_payload: dict[str, Any] = {
            "model": self.config.reasoning_model if reasoning else self.config.model,
            "messages": _clean_messages_for_request(messages),
            "response_format": {"type": "json_object"},
        }
        if reasoning:
            if self.config.reasoning_effort:
                request_payload["reasoning_effort"] = self.config.reasoning_effort
        else:
            request_payload["temperature"] = temperature
        payload = json.dumps(request_payload).encode("utf-8")
        request = Request(
            endpoint,
            data=payload,
            headers={
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urlopen(request, timeout=self.config.timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"{self.config.provider} HTTP {exc.code}: {error_body}") from exc
        except URLError as exc:
            raise RuntimeError(f"{self.config.provider} connection failed: {exc.reason}") from exc

        content = body["choices"][0]["message"]["content"]
        return _parse_json_content(content)


def load_llm_config(env_path: str | Path = ".env") -> LLMConfig:
    env_values = _read_env_file(env_path)
    provider = os.environ.get("LLM_PROVIDER") or env_values.get("LLM_PROVIDER") or "deepseek"
    base_url = os.environ.get("LLM_BASE_URL") or env_values.get("LLM_BASE_URL") or "https://api.deepseek.com"
    api_key = os.environ.get("LLM_API_KEY") or env_values.get("LLM_API_KEY")
    model = os.environ.get("LLM_MODEL") or env_values.get("LLM_MODEL") or "deepseek-chat"
    reasoning_model = (
        os.environ.get("LLM_REASONING_MODEL")
        or env_values.get("LLM_REASONING_MODEL")
        or os.environ.get("DEEPSEEK_REASONING_MODEL")
        or env_values.get("DEEPSEEK_REASONING_MODEL")
        or "deepseek-reasoner"
    )
    reasoning_effort = os.environ.get("LLM_REASONING_EFFORT") or env_values.get("LLM_REASONING_EFFORT")
    return LLMConfig(
        provider=provider,
        base_url=base_url,
        api_key=api_key,
        model=model,
        reasoning_model=reasoning_model,
        reasoning_effort=reasoning_effort,
    )


def _clean_messages_for_request(messages: list[dict[str, str]]) -> list[dict[str, str]]:
    cleaned: list[dict[str, str]] = []
    for message in messages:
        cleaned.append(
            {
                key: value
                for key, value in message.items()
                if key in {"role", "content", "name"} and value is not None
            }
        )
    return cleaned


def _parse_json_content(content: str) -> dict[str, Any]:
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:].strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"LLM returned non-JSON content: {content[:500]}") from exc


def _read_env_file(env_path: str | Path) -> dict[str, str]:
    path = Path(env_path)
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values
