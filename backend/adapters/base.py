"""适配器接口：ASR / TTS / OCR / Push。

规则（12 号 §4.4）：每个能力必须同时有真实现与假实现，测试默认用假实现。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class AdapterError(Exception):
    """适配器统一异常基类。"""


class UpstreamTimeout(AdapterError):
    """上游超时，可重试一次。"""


class QuotaExceeded(AdapterError):
    """配额或限流，不要重试，直接降级。"""


class EmptyResult(AdapterError):
    """上游返回空，按「没听清」处理，走求证。"""


class LowConfidence(AdapterError):
    """置信度过低，必须标记并求证，不得推断（R-2）。"""


@dataclass(frozen=True)
class AsrResult:
    text: str
    confidence: float


@dataclass(frozen=True)
class OcrResult:
    fields: dict[str, str]
    confidence: dict[str, float]


class Asr(Protocol):
    async def transcribe(self, pcm: bytes, sample_rate: int = 16000) -> AsrResult: ...


class Tts(Protocol):
    async def synthesize(self, text: str, rate: float = 0.86) -> bytes: ...


class Ocr(Protocol):
    async def extract(self, image: bytes) -> OcrResult: ...


class Push(Protocol):
    async def send(self, openid: str, template: str, data: dict[str, str]) -> bool: ...
