# backend/adapters/legacy —— 毕设旧系统的只读适配器

旧系统是毕设的 Django 医疗底座（端口 8001，库 ai250301，32 张表）。
我们**不改它一行代码**，只用 HTTP 只读调用 + 一次性导出数据。

## 边界

| 做 | 不做 |
| --- | --- |
| GET 查询检查项位置、科室字典 | 写、删、改任何数据 |
| 调用失败就降级到 fixtures | 在旧系统里加陪诊功能 |
| 只读调用集中在 client.py | 让业务代码直接访问 8001 |

## 降级链

旧系统可用 → 实时查询
旧系统 500 / 超时 / 没开 → 抛 LegacyUnavailable → 调用方读 fixtures/legacy/*.json

演示现场旧系统不一定开着，所以**降级路径必须有测试**，不能只在理想情况下跑通。

## 用法

~~~python
from backend.adapters.legacy.client import LegacyClient, LegacyUnavailable

client = LegacyClient("http://127.0.0.1:8001")
try:
    spots = client.find_location("彩超")
except LegacyUnavailable:
    spots = []   # 或读 fixtures
~~~

## 待办

- W2：与旧系统联调，确认 find_location 的真实返回结构，把契约写死；
- W4：如果旧系统数据已经导出并稳定，可以考虑把这个适配器降级为「仅演示兜底」；
- W6：决定是否彻底下线旧系统。
