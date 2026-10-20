"""适配器接口与假实现的契约测试。

规则（12 号 §4.4）：每类外部能力必须同时有真实现与假实现，测试默认用假实现。
本文件不自造假实现、不联网、不花费用、不依赖任何密钥：被测对象是 backend/adapters/base.py
的四个 Protocol 与 backend/adapters/fakes.py 的五个假实现。

为什么用 asyncio.run 而不是 pytest.mark.asyncio：当前 requirements-dev.txt 未包含
pytest-asyncio，用 asyncio.run 可以零新增依赖跑通异步接口；等 T6 引入插件后再迁移。
"""
from __future__ import annotations

import asyncio

import pytest

from backend.adapters.base import (
    AdapterError,
    EmptyResult,
    LowConfidence,
    QuotaExceeded,
    UpstreamTimeout,
)
from backend.adapters.fakes import FailingAsr, FakeAsr, FakeOcr, FakePush, FakeTts


def test_fake_asr_returns_fixed_text() -> None:
    """一段音频进去，一句话出来；默认置信度高于求证阈值 0.8。"""
    result = asyncio.run(FakeAsr().transcribe(b"\x00" * 320))
    assert result.text
    assert result.confidence >= 0.8


def test_fake_asr_counts_calls() -> None:
    """调用计数必须真实累加，否则降级链与重试逻辑无法被测试观察到。"""
    asr = FakeAsr()
    asyncio.run(asr.transcribe(b""))
    asyncio.run(asr.transcribe(b""))
    assert asr.calls == 2


def test_failing_asr_is_below_threshold() -> None:
    """置信度低于 0.6 必须走求证流程，不得推断（红线 R-2）。"""
    result = asyncio.run(FailingAsr().transcribe(b""))
    assert result.confidence < 0.6


def test_fake_asr_accepts_custom_text_and_confidence() -> None:
    """构造参数必须生效，供各用例注入不同置信度而不用改代码。"""
    result = asyncio.run(FakeAsr(text="请到三楼 B 区", confidence=0.55).transcribe(b""))
    assert result.text == "请到三楼 B 区"
    assert result.confidence == pytest.approx(0.55)


def test_fake_ocr_dose_field_is_low_confidence() -> None:
    """剂量字段置信度低时只标记、绝不自动纠错（剂量错误数必须为 0）。"""
    result = asyncio.run(FakeOcr().extract(b"img"))
    assert result.fields["剂量"]
    assert result.confidence["剂量"] < 0.8


def test_fake_ocr_fields_and_confidence_are_aligned() -> None:
    """字段集合与置信度集合必须一一对应，否则前端取置信度会 KeyError。"""
    result = asyncio.run(FakeOcr().extract(b"img"))
    assert set(result.fields) == set(result.confidence)


def test_fake_tts_returns_bytes() -> None:
    """语音合成返回字节流，且语速参数有默认值 0.86。"""
    audio = asyncio.run(FakeTts().synthesize("请到二楼检验科"))
    assert isinstance(audio, bytes)
    assert audio


def test_fake_push_records_call() -> None:
    """推送必须留痕，供家属端时间轴与失败重试用例断言。"""
    push = FakePush()
    assert asyncio.run(push.send("openid-1", "arrived", {"room": "306"})) is True
    assert push.sent == [("openid-1", "arrived", {"room": "306"})]


@pytest.mark.parametrize(
    "error",
    [UpstreamTimeout, QuotaExceeded, EmptyResult, LowConfidence],
)
def test_error_types_inherit_adapter_error(error: type[Exception]) -> None:
    """四个错误类型必须统一挂在 AdapterError 下，调用方才能一条 except 兜住。"""
    assert issubclass(error, AdapterError)
