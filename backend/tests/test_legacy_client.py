"""旧系统适配器与导出数据的测试。

原则：测试不联网。适配器的 transport 可注入，fixtures 是仓库内的文件。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.adapters.legacy.client import (
    FakeLegacy,
    LegacyClient,
    LegacyContractError,
    LegacyUnavailable,
    Location,
)


def ok_transport(url: str, body: bytes) -> str:
    assert "/ai/mixed/find_location/" in url
    assert json.loads(body.decode("utf-8"))["check_query"] == "彩超"
    return json.dumps(
        {"code": 200, "data": [{"room": "门诊三楼B区306"}, {"location": "门诊三楼眼科诊断区"}]},
        ensure_ascii=False,
    )


def retriever_down(url: str, body: bytes) -> str:
    return json.dumps({"code": 500, "msg": "Retriever not initialized"}, ensure_ascii=False)


def html_transport(url: str, body: bytes) -> str:
    return "<html>500 Internal Server Error</html>"


def test_find_location_ok() -> None:
    client = LegacyClient("http://127.0.0.1:8001", transport=ok_transport)
    spots = client.find_location("彩超")
    assert [s.room for s in spots] == ["门诊三楼B区306", "门诊三楼眼科诊断区"]
    assert all(s.source == "legacy" for s in spots)


def test_network_error_retried_then_unavailable() -> None:
    calls = {"n": 0}

    def flaky(url: str, body: bytes) -> str:
        calls["n"] += 1
        raise OSError("timeout")

    client = LegacyClient("http://127.0.0.1:8001", transport=flaky)
    with pytest.raises(LegacyUnavailable):
        client.find_location("彩超")
    assert calls["n"] == 2, "网络错误应重试一次"


def test_business_code_not_retried() -> None:
    calls = {"n": 0}

    def down(url: str, body: bytes) -> str:
        calls["n"] += 1
        return retriever_down(url, body)

    client = LegacyClient("http://127.0.0.1:8001", transport=down)
    with pytest.raises(LegacyUnavailable):
        client.find_location("彩超")
    assert calls["n"] == 1, "业务错误不重试"


def test_non_json_raises_contract_error() -> None:
    client = LegacyClient("http://127.0.0.1:8001", transport=html_transport)
    with pytest.raises(LegacyContractError):
        client.find_location("彩超")


def test_fixtures_check_items(repo_root: Path) -> None:
    path = repo_root / "fixtures" / "legacy" / "check_items.json"
    items = json.loads(path.read_text(encoding="utf-8"))
    assert len(items) >= 500, "检查项样本太少，导出可能失败"
    assert all(item["item_name"] and item["location"] for item in items)


def test_fixtures_departments_and_schedule(repo_root: Path) -> None:
    base = repo_root / "fixtures" / "legacy"
    departments = json.loads((base / "departments.json").read_text(encoding="utf-8"))
    samples = json.loads((base / "schedule_samples.json").read_text(encoding="utf-8"))
    assert len(departments) >= 20
    assert {"内科", "外科"} <= {d["name"] for d in departments}
    assert samples and isinstance(samples[0]["total"], int)
    assert samples[0]["doctor"].startswith("医生-"), "医生姓名必须已脱敏"


def test_fake_matches_keyword() -> None:
    fake = FakeLegacy([Location("彩超左肾", "三楼B区"), Location("CT 平扫", "一楼")])
    assert [loc.room for loc in fake.find_location("彩超")] == ["三楼B区"]
