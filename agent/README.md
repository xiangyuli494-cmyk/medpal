# MedPal-Cog 骨架（agent/）

> 这是赛题3方案第 3 章的**可运行最小实现**。不含 Nexent 本体（要 Docker），其余全部能在本机跑。
> 目的：让 W1 的任务从「从零搭」变成「装 Docker + 喂真数据」。

---

## 1 十秒验证它能跑

~~~bash
cd agent
export PYTHONIOENCODING=utf-8            # Windows 控制台不加这个中文全乱码
/e/Python/python.exe mcp-server/seed.py --reset      # 建种子库（17 三元组 + 1 资产 + 15 锚点）
/e/Python/python.exe tests/test_smoke.py             # 纯离线，应输出 ALL PASS
/e/Python/python.exe eval/run_eval.py                # 14 条评测，出报告到 eval/reports/
~~~

预期：smoke 输出 `ALL PASS`；eval 输出 `科室准确率：100%` 等六行 + 报告路径。

## 2 目录与职责

| 路径 | 是什么 | 谁维护 |
| --- | --- | --- |
| `mcp-server/server.py` | FastMCP 入口，注册 10 个工具（7 个必做 + 3 个辅助） | T1 |
| `mcp-server/store.py` | SQLite：资产台账 / 三元组 / 版本快照 / trace / 对齐别名 | T3 |
| `mcp-server/parsers.py` | 解析与实体识别（文本、PDF、表格），`ENTITY_HINTS` + `SYNONYMS` 在这里 | T2 |
| `mcp-server/seed.py` | 种子本体与样例资产，`--reset` 可重建；锚点由真实解析产生，不是手写的 | T3 |
| `skills/s1-asset-audit/` | 技能包：资产盘点与卡片生成 | T4 |
| `skills/s2-ontology-evolve/` | 技能包：本体候选抽取 → 校验 → 提交 | T4 |
| `skills/s3-evidence-decision/` | 技能包：检索-推理双驱动，输出可溯源决策链 | T4 |
| `eval/run_eval.py` | 离线评测，不调大模型，秒级出分 | T5 |
| `tests/` | 冒烟（离线）/ stdio 客户端 / streamable-http 客户端 | T6 |

## 3 三种接入方式（对应 Nexent 的三条路）

### 3.1 stdio —— 本地调试 / MCP Inspector

~~~bash
/e/Python/python.exe mcp-server/server.py
~~~

### 3.2 streamable-http —— Nexent「远程链接」用这条

~~~bash
MCP_TRANSPORT=streamable-http /e/Python/python.exe mcp-server/server.py
# 另一终端验证（注意两行 NO_PROXY，见第 5 节）
NO_PROXY=127.0.0.1,localhost no_proxy=127.0.0.1,localhost \
  /e/Python/python.exe tests/test_http_client.py
~~~

端点：`http://<host>:8090/mcp`。Nexent 里填远程 MCP 链接时 host 用 `host.docker.internal`（容器内访问宿主机）。

### 3.3 API 转 MCP —— 兜底

`server.py` 的工具签名就是 REST 语义，真要兜底时用 Nexent 的「API 转 MCP」贴一份 OpenAPI 3.x 即可，不需要改代码。

## 4 十个工具

| 工具 | 对应赛题 | 一句话 |
| --- | --- | --- |
| `ingest_asset` | R1 | 吃一份文件，解析、抽实体、生成 Asset Card 与锚点 |
| `get_asset_card` | R1 | 按 id / 模态 / 实体查卡片 |
| `kg_query` | R2 | 从种子实体出发取 k 跳路径，每条带 triple_id 与 provenance |
| `onto_propose` | R2 | 从资产里抽候选三元组，进待审队列（不直接入库） |
| `onto_commit` | R2 | 人工确认后提交，版本号 +1，生成快照 |
| `std_align` | R2 | 实体 → ICD-10 映射，返回 exact / fuzzy / none |
| `trace_write` | R4 | 落决策链，算溯源完整率，出 Markdown 报告 |
| `skill_export` | R4 | 把一条 trace 的步骤序列导成 SKILL.md 草稿 |
| `kb_search` | 辅助 | 透传 Nexent 知识库检索（未配 `KB_ENDPOINT` 时返回配置提示） |
| `health` | 辅助 | 版本、库路径、三元组数、当前本体版本 |

约定：所有工具返回 `{"ok": true/false, ...}`；`ok=false` 时必须带 `reason` 与 `hint`，不许静默失败。

## 5 两个必踩的坑（写在这，别浪费半天）

1. **中文乱码**：Windows 控制台默认 GBK。任何跑 Python 的命令前加 `PYTHONIOENCODING=utf-8`，否则报告文件正常、终端全乱码。
2. **502 Bad Gateway**：系统级代理会拦 `127.0.0.1:8090`。即使 `env` 里看不到 `HTTP_PROXY`，也必须显式 `NO_PROXY=127.0.0.1,localhost no_proxy=127.0.0.1,localhost`。现象是 httpx 报 `Server error 502 for url http://127.0.0.1:8090/mcp`，看着像服务没起，其实是代理吞了。

## 6 已知边界

- 本体只有 17 条三元组、1 份资产，是**种子**不是数据。真数据要等 OpenCMKG 裁剪（W1 T3）。
- 评测 14 条、分数全 100%，**不能当答辩分数**。它跑规则化链路、题是自己出的，只用于回归与上限参照。真实分数要在 Nexent 里跑同一份 dataset。
- `kb_search` 是 stub，真检索走 Nexent 的 `search-knowledge-base` 技能。
- 无 Dockerfile，容器化在 W2。

## 7 下一步（W1 待办）

| 事项 | 人 | 验收 |
| --- | --- | --- |
| 装 WSL2 + Docker Desktop，起 Nexent | T1 | 控制台能登录 |
| 写 Dockerfile + compose，MCP 进容器 | T1 | 容器内 `health` 返回 ok |
| OpenCMKG 裁 8 万条灌进 SQLite | T3 | `health` 的 triples 到 8 万量级 |
| 40 份公开样本入库 | T2 | 台账 40 张卡片 |
| 评测集补到 30 条 | T5 | `v0.jsonl` 30 行 |
| ruff + CI | T6 | PR 自动跑三套测试 |
