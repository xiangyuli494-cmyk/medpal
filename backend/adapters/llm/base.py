"""LLM 适配器的接口与异常。"""

from __future__ import annotations

from typing import Protocol


class LlmError(Exception):
    """LLM 调用失败的统一异常。"""


class LlmConfigError(LlmError):
    """配置缺失或不可用。"""


class LlmDisabled(LlmError):
    """LLM_ENABLED=False，调用方应降级到规则层。"""


class LlmResponseError(LlmError):
    """上游返回结构不符合预期。"""


class LlmClient(Protocol):
    """最小 LLM 接口：一次 chat completion，返回 assistant message。"""

    def chat(self, messages: list[dict], tools: list[dict]) -> dict:
        """发送 messages 与 tools，返回 assistant message。"""
