"""测试用假 LLM：按脚本返回 assistant message，零网络、零费用。"""

from __future__ import annotations

from collections.abc import Iterable

from .base import LlmError


class FakeLlm:
    """按顺序返回预置响应的 LLM，便于测试工具调用循环。"""

    def __init__(self, responses: Iterable[dict]) -> None:
        self._responses = list(responses)
        self.calls: list[dict] = []

    def chat(self, messages: list[dict], tools: list[dict]) -> dict:
        self.calls.append({"messages": list(messages), "tools": list(tools)})
        if not self._responses:
            raise LlmError("FakeLlm 没有更多预置响应")
        return self._responses.pop(0)
