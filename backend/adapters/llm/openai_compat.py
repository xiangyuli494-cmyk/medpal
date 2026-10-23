"""OpenAI-compatible chat completions 适配器（DashScope/MaaS 等）。"""
from __future__ import annotations

import httpx

from .base import (
    LlmConfigError,
    LlmDisabled,
    LlmError,
    LlmResponseError,
)
from .config import LlmConfig


class OpenAICompatibleLlm:
    """用 httpx 调 /chat/completions，支持 tool calling。"""

    def __init__(self, config: LlmConfig, client: httpx.Client | None = None) -> None:
        self.config = config
        self._client = client or httpx.Client(timeout=config.timeout)

    def close(self) -> None:
        self._client.close()

    def chat(self, messages: list[dict], tools: list[dict]) -> dict:
        if not self.config.enabled:
            raise LlmDisabled("LLM_ENABLED=False")
        if not self.config.api_key:
            raise LlmConfigError("缺少 LLM_API_KEY")
        if not self.config.base_url:
            raise LlmConfigError("缺少 LLM_BASE_URL")

        payload: dict = {
            "model": self.config.model,
            "messages": messages,
            "temperature": 0,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        try:
            response = self._client.post(
                f"{self.config.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.config.api_key}"},
                json=payload,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text.strip()[:500]
            raise LlmError(
                f"LLM 请求失败: HTTP {exc.response.status_code}: {detail}"
            ) from exc
        except httpx.HTTPError as exc:
            raise LlmError(f"LLM 请求失败: {exc}") from exc

        try:
            data = response.json()
            message = data["choices"][0]["message"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise LlmResponseError("LLM 返回结构不符合预期") from exc

        if not isinstance(message, dict):
            raise LlmResponseError("LLM 返回的 message 不是对象")
        return message
