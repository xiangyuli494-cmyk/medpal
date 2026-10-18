"""毕设旧系统的只读适配器。

边界（docs/specs/legacy-reuse.md）：
- 只读：只发查询请求，不写、不删、不改；
- 超时短、最多重试一次；失败一律抛 LegacyUnavailable，由调用方降级到 fixtures；
- 不 import Django、不连旧库，走 HTTP 调旧系统（默认 8001）。

已知事实（W1 读旧代码得到）：
- 接口是 POST /ai/mixed/find_location/，body 为 {"check_query": "..."}；
- 返回 {"code": 200, "data": [...]}，code 非 200 表示异常；
- 该接口依赖 Milvus/Neo4j 混合检索，干净机器上会返回
  {"code":500,"msg":"Retriever not initialized"}，所以 fixtures 是主路径，适配器只是可选增强。

W2 的用法：
    client = LegacyClient(os.environ["LEGACY_BASE_URL"])
    try:
        spots = client.find_location("彩超")
    except LegacyUnavailable:
        spots = []   # 或读 fixtures/legacy/check_items.json
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable

DEFAULT_TIMEOUT = 2.0
LOCATION_PATH = "/ai/mixed/find_location/"

Transport = Callable[[str, bytes], str]


class LegacyUnavailable(Exception):
    """旧系统不可用：超时、连不上、5xx、业务 code 非 200。调用方应降级。"""


class LegacyContractError(LegacyUnavailable):
    """返回了内容但不是我们认识的形状，属于契约漂移，要报给 T1。"""


@dataclass(frozen=True)
class Location:
    item_name: str
    room: str
    source: str = "legacy"


def _urllib_transport(url: str, body: bytes) -> str:
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=DEFAULT_TIMEOUT) as resp:  # noqa: S310
        return resp.read().decode("utf-8", errors="replace")


class LegacyClient:
    def __init__(
        self,
        base_url: str,
        timeout: float = DEFAULT_TIMEOUT,
        transport: Transport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._transport = transport or _urllib_transport

    def _post(self, path: str, payload: dict[str, str]) -> dict:
        url = self.base_url + path
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")

        last_error: Exception | None = None
        for _ in range(2):  # 最多两次，只对网络错误重试
            try:
                raw = self._transport(url, body)
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                last_error = exc
                continue
            try:
                data = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise LegacyContractError(f"旧系统返回的不是 JSON：{exc}") from exc
            if not isinstance(data, dict):
                raise LegacyContractError("旧系统返回的顶层不是对象")
            code = data.get("code", 200)
            if code != 200:
                raise LegacyUnavailable(f"旧系统返回 code={code}：{data.get('msg', '')}")
            return data
        raise LegacyUnavailable(f"旧系统不可用：{last_error}")

    def find_location(self, item_name: str) -> list[Location]:
        """按检查项目名查院内位置。"""
        payload = self._post(LOCATION_PATH, {"check_query": item_name})
        rows = payload.get("data", [])
        if not isinstance(rows, list):
            raise LegacyContractError("find_location 返回的 data 不是数组")
        result: list[Location] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            room = row.get("room") or row.get("location") or row.get("wzsm") or ""
            if room:
                result.append(Location(item_name=item_name, room=str(room)))
        return result


class FakeLegacy:
    """测试与离线演示用：不联网，按关键词在给定列表里找。"""

    def __init__(self, locations: list[Location] | None = None, fail: bool = False) -> None:
        self.locations = locations or []
        self.fail = fail

    def find_location(self, item_name: str) -> list[Location]:
        if self.fail:
            raise LegacyUnavailable("fake failure")
        return [loc for loc in self.locations if item_name in loc.item_name]
