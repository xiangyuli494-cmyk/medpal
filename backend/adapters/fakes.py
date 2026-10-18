"""假实现：测试与本地开发默认使用，零网络、零费用、结果稳定。"""
from __future__ import annotations

from .base import AsrResult, OcrResult


class FakeAsr:
    def __init__(self, text: str = "抽血在二楼检验科", confidence: float = 0.92) -> None:
        self.text = text
        self.confidence = confidence
        self.calls = 0

    async def transcribe(self, pcm: bytes, sample_rate: int = 16000) -> AsrResult:
        self.calls += 1
        return AsrResult(text=self.text, confidence=self.confidence)


class FailingAsr:
    """测试降级链用：返回低置信度，验证系统必须求证而不是猜。"""

    async def transcribe(self, pcm: bytes, sample_rate: int = 16000) -> AsrResult:
        return AsrResult(text="嗯……那个……", confidence=0.41)


class FakeTts:
    async def synthesize(self, text: str, rate: float = 0.86) -> bytes:
        return b"RIFF_fake_wav_" + text.encode("utf-8")[:32]


class FakeOcr:
    async def extract(self, image: bytes) -> OcrResult:
        return OcrResult(
            fields={"药品": "阿司匹林肠溶片", "剂量": "100mg", "频次": "每日一次"},
            confidence={"药品": 0.95, "剂量": 0.61, "频次": 0.88},
        )


class FakePush:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str, dict[str, str]]] = []

    async def send(self, openid: str, template: str, data: dict[str, str]) -> bool:
        self.sent.append((openid, template, data))
        return True

# harmless comment to change code only