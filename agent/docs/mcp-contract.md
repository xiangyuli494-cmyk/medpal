# MedPal-Cog MCP 工具契约 v1

> 交付物 1.1 · T1 xiangyuli494-cmyk · 2026-10-25 · 状态：**冻结候选**
> 适用对象：T2/T4 的实现、T6 的 client 与 CI 门禁、Nexent 挂载配置
> 唯一事实来源：`agent/mcp-server/server.py`、`agent/mcp-server/store.py`。本文与代码冲突时以代码为准，并**改文档**。

---

## 0. 服务信息

### 0.1 服务标识

| 项 | 值 | 定义位置 |
| --- | --- | --- |
| MCP server name | `medpal-cog` | `server.py:29` |
| server_version | `0.1.0` | `server.py:27` |
| 工具数 | 10（核心 7 + 辅助 3） | `server.py` 中 `@mcp.tool()` 装饰的 10 个函数 |
| 官方 SDK | `mcp`（`mcp.server.fastmcp.FastMCP`） | `server.py:25` |

核心 7 个直接对应赛题要求，辅助 3 个是工程配套，**都不删**：

| 类别 | 工具 | 对应要求 |
| --- | --- | --- |
| 核心 | `ingest_asset`、`get_asset_card` | R1 多模态资产识别与标识 |
| 核心 | `kg_query`、`onto_propose`、`onto_commit`、`std_align` | R2 本体半自动构建与标准对齐 |
| 核心 | `trace_write` | R4 跨文档推理与决策链溯源 |
| 辅助 | `skill_export` | R3 以 Skill 形式复用决策链 |
| 辅助 | `kb_search` | R3 知识库检索透传 |
| 辅助 | `health` | 冒烟与 CI 门禁 |

> R3 的正式承载方式是「10 个工具以 MCP 暴露给 Nexent + 三个 Skill 包编排」，不是单个工具。

### 0.2 两种连接方式

```bash
# ① stdio（本地调试、MCP Inspector、T6 的 CI client）——默认
python server.py

# ② streamable-http（Nexent「远程链接」用）
MCP_TRANSPORT=streamable-http python server.py
```

| 项 | stdio | streamable-http |
| --- | --- | --- |
| 入口 | stdin/stdout | `http://{MCP_HOST}:{MCP_PORT}/mcp` |
| 默认地址 | — | `0.0.0.0:8090`，路径固定 `/mcp` |
| 会话 | 单进程一次 | `stateless_http=True`（无会话保持，可并发） |
| 定义位置 | `server.py:37` | `server.py:34-37` |

> Nexent 容器内访问宿主机服务时用 `host.docker.internal:8090`，不要写 `127.0.0.1`——容器里的回环是容器自己。
>
> Windows 上默认开着系统代理（本机实测 `127.0.0.1:7892`，注册表 `HKCU\...\Internet Settings\ProxyServer`），httpx 的 `trust_env=True` 会读它，导致连 `127.0.0.1:8090` 被转发到代理并回 `502 Bad Gateway`——看起来像服务没起，实际是客户端走了代理。`tests/test_http_client.py` 已用 `trust_env=False` 造 httpx client 避开；自己另写 client 时照抄 `_no_proxy_client`。

### 0.3 环境变量

| 变量 | 默认 | 作用 |
| --- | --- | --- |
| `MCP_TRANSPORT` | `stdio` | `stdio` \| `streamable-http` |
| `MCP_HOST` | `0.0.0.0` | HTTP 监听地址 |
| `MCP_PORT` | `8090` | HTTP 监听端口 |
| `MEDPAL_DB` | `agent/mcp-server/data/medpal.db` | SQLite 库路径；测试时指向副本，别动主库 |
| `KB_ENDPOINT` | 空 | 非空时 `kb_search` 才真正转发；空则返回 `kb_not_configured` |

### 0.4 运行依赖

`mcp`、`pymupdf`（PDF，缺则 `parser_unavailable`）、`openpyxl`（xlsx，缺则 `parser_unavailable`）。文本 / CSV / 图片侧车走标准库，无第三方依赖。

---

## 1. 通用约定

### 1.1 返回信封

所有工具**永远返回 dict，从不抛异常给调用方**。两种形态：

```json
{"ok": true,  ...业务字段}
{"ok": false, "reason": "<错误码>", "hint": "<人话>", ...回显入参}
```

- `ok` 必存在，`bool`；
- 失败时 `reason` 必存在，取值见 §3 的错误码总表；`hint` 必存在（可为空串）；
- 失败时**回显关键入参**（如 `asset_id`、`diff_id`、`input`），便于 Agent 自己纠错重试；
- 实现见 `server.py:45-53`（`_ok()` / `_err()`）。

**只有一种例外**：`kg_query` 的 `no_path` 会带上完整查询现场（`version`/`resolved`/`unresolved`/`paths`），因为它不是"调用错了"，而是"查了但没连上"，Agent 需要看到 `unresolved` 才能换词重查。

### 1.2 标识符规范

| 前缀 | 含义 | 生成规则 | 例 |
| --- | --- | --- | --- |
| `AST-<年>-<6位hex>` | 资产 | `store.py:123` | `AST-2026-000137` |
| `T-<8位hex>` | 三元组 | `store.py:184` | `T-d331cf32` |
| `DF-<8位hex>` | 待审 diff | `server.py:286` | `DF-758a0f0a` |
| `TR-<yyyymmdd>-<4位hex大写>` | 决策链 | `store.py:504` | `TR-20261025-D2C1` |
| `v<主>.<次>` | 本体快照版本 | `server.py:341` `_bump()` | `v0.9` → `v1.0` |

**锚点（anchor_id）= `<asset_id>#<位置>`**，位置编码按模态分四种，这是溯源能点回原文的根：

| 模态 | 位置格式 | 例 |
| --- | --- | --- |
| `text`（.md/.txt） | `s{节}.h` 标题 / `s{节}.p{段}.c{句}` 句子 | `AST-2026-000137#s2.p1.c3` |
| `pdf_text` | `p{页}.t{表}.r{行}` 表格行 / `p{页}.s1` 整页 | `AST-2026-000137#p3.t1.r2` |
| `table`（.csv/.xlsx） | `t1.r{行}` | `AST-2026-59622c#t1.r2` |
| `image_report` | `img.r{区}` | `AST-2026-000137#img.r1` |

### 1.3 provenance 硬约束（贯穿全部工具）

**任何结论都必须带 `asset_id` / `anchor_id` / `triple_id`；拿不到证据就返回 `ok:false` 说缺口，不许编。**

落在契约上是三条：

1. `kg_query` 返回的每个 `steps[]` 项必带 `provenance{asset_id, anchor_id}`；
2. `onto_propose` 的每个候选必带 `provenance`，`anchor_id` 指不到原文的进 `rejected`；
3. `trace_write` 按证据是否可解析算「溯源完整率」，指不到的进 `unresolved` 且**扣分**。

### 1.4 本体词表（v1 冻结，`onto_propose` 只在此空间内产出）

实体 6 类：`Disease` `Symptom` `Exam` `Drug` `Finding` `Department`
关系 8 类：`has_symptom` `diagnosed_by` `treated_by` `contraindicated_for` `requires_exam` `belongs_to_dept` `subclass_of` `aligned_to_standard`

`source_type` 三值锁死「这条知识该由谁背书」：`icd10` / `pathway` / `drug_label`。

> **v1 落地现状（写清楚，别让下游猜）**：`onto_propose` 的规则抽取器（`server.py:153-173`）目前只识别 3 类句式 → `requires_exam` / `contraindicated_for` / `may_cause`。其中前两类在词表内，`may_cause` **不在** 8 类里——2026-10-29 已裁定把它加为第 9 类，随 schema v1 在 W3 与 `v1.0` 快照一起落地（见 `agent/docs/ontology-schema.md` §9 第 3 条），在此之前它只能作为 `pending` 候选、不入库。种子库 `v0.9` 实际含 6 类关系，缺 `treated_by` / `subclass_of`。这是**已知缺口**，不是契约缺失：schema 允许 8 类，抽取器覆盖 2 类有效关系，其余走 LLM few-shot（T4 负责）。

### 1.5 幂等与副作用

| 工具 | 写库 | 可重复调用 |
| --- | --- | --- |
| `ingest_asset` | 是（asset 表） | 每次生成**新** `asset_id`，同文件重复入库会产生多张卡 |
| `onto_propose` | 是（pending_diff 表） | 每次生成**新** `diff_id`，只写待审队列，不动本体 |
| `onto_commit` | 是（triple + version + 快照文件） | 同一 `diff_id` 二次提交：diff 状态已 `committed`，`added=0`，但**仍会生成新快照** |
| `trace_write` | 是（trace 表 + `reports/*.md`） | 每次新 `trace_id` |
| `kg_query` / `get_asset_card` / `std_align` / `skill_export` / `kb_search` / `health` | 否 | 纯读 |

⚠️ `store.snapshot()` 的落盘目录写死 `DATA_DIR`（`store.py:376`），**不跟随 `MEDPAL_DB`**。测试用副本库时仍会往 `agent/mcp-server/data/` 写 `ontology_v*.jsonl`，跑完需清理。

---

## 2. 工具清单

### 2.1 `ingest_asset` — 解析文件、生成资产卡与锚点

```python
ingest_asset(path: str, modality: str = "", title: str = "",
             source_type: str = "public_standard", ingested_by: str = "") -> dict
```

**入参**

| 名 | 类型 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `path` | str | 是 | — | 文件路径，服务端本地可读 |
| `modality` | str | 否 | `""` | 留空按扩展名自动判别 |
| `title` | str | 否 | `""` | 留空取文档标题 |
| `source_type` | str | 否 | `public_standard` | `public_standard` → `sensitivity=public`；其他值 → `synthetic` |
| `ingested_by` | str | 否 | `""` | 入库人代号，写进资产卡 |

模态自动判别（`parsers.REGISTRY`，`parsers.py:192`）：`.md/.txt`→`text`；`.pdf`→`pdf_text`；`.csv/.xlsx`→`table`；`.png/.jpg/.jpeg/.webp`→`image_report`。

**出参**

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `ok` | bool | |
| `asset_id` | str | 新资产号 |
| `modality` | str | 实际判别结果 |
| `anchors` | list | 可引用单元，每项 `{anchor_id, kind, text}` |
| `entity_hint` | list[str] | 正则猜出的实体，仅供 `onto_propose` 参考 |
| `blocks` | int | 解析出的块数 |

**真实请求 / 响应**（`agent/data/samples/pathway_k27.md`，anchors 截前 3 条）

```json
// 请求
{"path": "agent/data/samples/pathway_k27.md", "source_type": "public_standard", "ingested_by": "T1"}

// 响应
{
  "ok": true,
  "asset_id": "AST-2026-0a8a28",
  "modality": "text",
  "anchors": [
    {"anchor_id": "AST-2026-0a8a28#s1.h", "kind": "section",
     "text": "消化性溃疡临床路径（2023 版）摘要"},
    {"anchor_id": "AST-2026-0a8a28#s2.h", "kind": "section", "text": "诊断依据"},
    {"anchor_id": "AST-2026-0a8a28#s2.p1.c1", "kind": "sentence",
     "text": "患者以上腹部痛为主要表现，疼痛多位于上腹中部偏右"}
  ],
  "entity_hint": ["消化性溃疡", "上腹隐痛", "胃镜", "幽门螺杆菌", "布洛芬"],
  "blocks": 9
}
```

**错误**

```json
{"ok": false, "reason": "file_not_found", "hint": "检查路径是否存在：agent/data/samples/nope.md"}
{"ok": false, "reason": "no_parser", "hint": "该扩展名暂无解析器，请在 parsers.REGISTRY 注册", "suffix": ".xyz"}
{"ok": false, "reason": "parser_unavailable", "hint": "<解析器自报原因，如 pymupdf_not_installed>", "path": "..."}
```

`file_not_found` `no_parser` `parser_unavailable`

---

### 2.2 `get_asset_card` — 查资产卡

```python
get_asset_card(asset_id: str = "", modality: str = "",
               entity: str = "", limit: int = 20) -> dict
```

**入参**

| 名 | 类型 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `asset_id` | str | 否 | `""` | 给了就精确取一张 |
| `modality` | str | 否 | `""` | 按模态过滤 |
| `entity` | str | 否 | `""` | 按实体过滤 |
| `limit` | int | 否 | 20 | 列表上限 |

三个查询条件都为空 → 返回最近入库的资产列表。

**出参**：`ok`、`cards[]`；列表模式多一个 `count`。`cards[]` 项是资产卡：

```json
{
  "asset_id": "AST-2026-000137",
  "title": "消化性溃疡临床路径（2023 版）摘要",
  "modality": "text",
  "source": {"type": "public_standard", "publisher": "国家卫生健康委",
             "path": "agent/data/samples/pathway_k27.md"},
  "version": {"value": "2023", "captured_at": "2026-10-25T17:03:51+08:00", "supersedes": null},
  "sensitivity": "public",
  "structure": {"blocks": 9, "anchors": 15, "kinds": ["heading", "paragraph"]},
  "anchors": [{"anchor_id": "AST-2026-000137#s1.h", "kind": "section",
               "text": "消化性溃疡临床路径（2023 版）摘要"}, "..."],
  "entities": ["消化性溃疡", "上腹隐痛", "胃镜", "幽门螺杆菌", "布洛芬"],
  "kb": {"base": "med-text", "doc_id": "AST-2026-000137", "status": "ready"},
  "ingested_by": "T2",
  "created_at": "2026-10-25T17:03:51+08:00"
}
```

**真实请求 / 响应**（按实体过滤，`cards` 截断）

```json
// 请求
{"entity": "胃镜"}
// 响应
{"ok": true, "count": 1, "cards": [{"asset_id": "AST-2026-000137", "...": "同上"}]}
```

**错误**

```json
{"ok": false, "reason": "asset_not_found", "hint": "先跑 ingest_asset", "asset_id": "AST-9999-000000"}
```

---

### 2.3 `kg_query` — 多跳本体查询（核心中的核心）

```python
kg_query(seed_entities: list[str], max_hops: int = 2,
         rel_filter: list[str] = None, limit: int = 20) -> dict
```

**入参**

| 名 | 类型 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `seed_entities` | list[str] | 是 | — | 种子实体表面串，内部走 `alias` 表归一 |
| `max_hops` | int | 否 | 2 | 最大跳数；`3` 才够跑通「症状→病→检查→并发症」演示链 |
| `rel_filter` | list[str] | 否 | `null` | 只走这些关系 |
| `limit` | int | 否 | 20 | 路径数上限 |

**出参**

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `ok` | bool | 有路径才 true |
| `version` | str | 查询时的本体版本 |
| `resolved` | list[str] | 归一成功的节点 id |
| `unresolved` | list[str] | 归一失败的表面串——**Agent 靠它换词重查** |
| `paths` | list | 路径列表，见下 |
| `reason` | str \| null | 无路径时 `"no_path"` |

`paths[]` 项：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `nodes` | list[str] | 节点 id 序列，长度 = `hops + 1` |
| `hops` | int | 跳数 |
| `steps` | list | 每条边一项，见下 |
| `provenance` | list | 边上所有 `{asset_id, anchor_id}` 去重后拼接 |
| `score` | float | 各边 confidence 的均值，3 位小数 |

`steps[]` 项：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `triple_id` | str | |
| `edge` | str | 人话：「上腹隐痛 -[diagnosed_by]-> 消化性溃疡」 |
| `rel` | str | 关系名 |
| `head_id` / `head_label` / `head_type` | str | 头实体 |
| `tail_id` / `tail_label` / `tail_type` | str | 尾实体 |
| `provenance` | object | `{asset_id, anchor_id}` |
| `confidence` | float | 该边置信度 |

**排序规则**：`(-hops, -score)` —— 先按跳数降序（路径越长越靠前，因为更能体现推理），同跳数按分数降序（`store.py:243-348`）。

**真实请求 / 响应**（`max_hops=2`，`paths` 截第 1 条）

```json
// 请求
{"seed_entities": ["上腹隐痛"], "max_hops": 2}

// 响应
{
  "ok": true,
  "version": "v0.9",
  "resolved": ["SYM-EPI"],
  "unresolved": [],
  "paths": [
    {
      "nodes": ["SYM-EPI", "K27", "ICD10-K27"],
      "hops": 2,
      "steps": [
        {"triple_id": "T-d331cf32", "edge": "上腹隐痛 -[diagnosed_by]-> 消化性溃疡",
         "rel": "diagnosed_by", "head_id": "SYM-EPI", "head_label": "上腹隐痛",
         "head_type": "Symptom", "tail_id": "K27", "tail_label": "消化性溃疡",
         "tail_type": "Disease",
         "provenance": {"asset_id": "AST-2026-000137", "anchor_id": "AST-2026-000137#s2.p1.c3"},
         "confidence": 0.78},
        {"triple_id": "T-b5d99245", "edge": "消化性溃疡 -[aligned_to_standard]-> ICD-10 K27",
         "rel": "aligned_to_standard", "head_id": "K27", "head_label": "消化性溃疡",
         "head_type": "Disease", "tail_id": "ICD10-K27", "tail_label": "ICD-10 K27",
         "tail_type": "Disease",
         "provenance": {"asset_id": "AST-2026-000137", "anchor_id": "AST-2026-000137#s1.h"},
         "confidence": 0.99}
      ],
      "provenance": [
        {"asset_id": "AST-2026-000137", "anchor_id": "AST-2026-000137#s2.p1.c3"},
        {"asset_id": "AST-2026-000137", "anchor_id": "AST-2026-000137#s1.h"}
      ],
      "score": 0.885
    }
  ],
  "reason": null
}
```

**三跳真实样例**（`max_hops=3`，截第 1 条）—— 这是答辩要现场打的那条链：

```json
{
  "nodes": ["SYM-EPI", "DEP-GI", "K21", "ICD10-K21"],
  "hops": 3,
  "score": 0.89,
  "steps": [
    {"edge": "上腹隐痛 -[belongs_to_dept]-> 消化内科", "triple_id": "T-c81c915c",
     "provenance": {"asset_id": "AST-2026-000137", "anchor_id": "AST-2026-000137#s2.p1.c2"},
     "confidence": 0.8},
    {"edge": "胃食管反流病 -[belongs_to_dept]-> 消化内科", "triple_id": "T-3604ada3",
     "confidence": 0.88},
    {"edge": "胃食管反流病 -[aligned_to_standard]-> ICD-10 K21", "triple_id": "T-5d2c1402",
     "confidence": 0.99}
  ]
}
```

**错误**

```json
// 归一失败 / 无路径：注意 ok=false 但带完整现场
{"ok": false, "version": "v0.9", "resolved": [], "unresolved": ["不存在的实体"],
 "paths": [], "reason": "no_path"}

// 空种子
{"ok": false, "reason": "no_seed", "hint": "种子实体为空，先做实体归一"}
```

`no_path` `no_seed`

---

### 2.4 `onto_propose` — 抽取候选三元组，产出待审 diff

```python
onto_propose(asset_ids: list[str], scope: str = "") -> dict
```

**入参**

| 名 | 类型 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `asset_ids` | list[str] | 是 | — | 要抽的资产；不存在的进 `rejected`，不中断 |
| `scope` | str | 否 | `""` | 标注抽取范围，原样回传，仅作说明 |

**只写 `pending_diff` 表，不动本体。** 低资源策略 = 约束输出空间：只允许 3 类句式模板 + 六类实体 / 八类关系；规则校验在前（类型匹配、重复、空头尾），通过的才进待审队列（`server.py:180-300`）。

**出参**

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `ok` | bool | **恒为 true**（抽取本身不失败；抽空也是成功，看 `counts`） |
| `diff_id` | str | 待审批次号，交给 `onto_commit` |
| `scope` | str | 原样回传 |
| `candidates` | list | 候选三元组，见下 |
| `rejected` | list | 被拒项，见下 |
| `counts` | object | `{candidates, rejected}` |

`candidates[]` 项：

```json
{
  "head": {"id": "K27", "type": "Disease", "label": "消化性溃疡"},
  "rel": "requires_exam",
  "tail": {"id": "EX-GASTRO", "type": "Exam", "label": "胃镜"},
  "confidence": 0.72,
  "provenance": {"asset_id": "AST-2026-000137", "anchor_id": "AST-2026-000137#s3.p1.c2"}
}
```

`confidence` 固定 0.72（规则抽取的保守先验，等人工确认后再上调）。

`rejected[]` 项两种形态，`reason` 四值之一：

| reason | 触发行 | 含义 |
| --- | --- | --- |
| `asset_not_found` | `server.py:216` | 资产号不存在 |
| `too_short` | `server.py:221` | 锚点文本 < 12 字（方案原写 30 字，2026-10-29 裁定**以 12 为准**，见 `agent/docs/ontology-schema.md` §7） |
| `no_pattern_match` | `server.py:246` | 锚点没有任何句式命中 |
| `entity_unresolved` | `server.py:260` | 头或尾落不到已有节点 |
| `duplicate` | `server.py:279` | `(head, rel, tail)` 已有 active 记录（`contraindicated_for` 反向也算重复） |

```json
{"anchor_id": "AST-2026-000137#s2.h", "reason": "too_short"}
{"candidate": "消化性溃疡-requires_exam->胃镜", "reason": "duplicate"}
```

**真实请求 / 响应**（同一文档已入库，故候选全被判重；`counts` 保持真实）

```json
// 请求
{"asset_ids": ["AST-2026-000137"]}

// 响应
{
  "ok": true,
  "diff_id": "DF-758a0f0a",
  "scope": "",
  "candidates": [],
  "rejected": [
    {"anchor_id": "AST-2026-000137#s1.h", "reason": "no_pattern_match"},
    {"anchor_id": "AST-2026-000137#s2.h", "reason": "too_short"},
    {"candidate": "消化性溃疡-requires_exam->幽门螺杆菌呼气试验", "reason": "duplicate"},
    {"candidate": "消化性溃疡-requires_exam->胃镜", "reason": "duplicate"},
    {"candidate": "消化性溃疡-contraindicated_for->布洛芬", "reason": "duplicate"}
  ],
  "counts": {"candidates": 0, "rejected": 15}
}
```

**抽取成功的形状**（同一份文档、库里还没有这些边时）：

```json
{"candidates": [
  {"head": {"id": "K27", "type": "Disease", "label": "消化性溃疡"},
   "rel": "requires_exam",
   "tail": {"id": "EX-HP-BT", "type": "Exam", "label": "幽门螺杆菌呼气"},
   "confidence": 0.72,
   "provenance": {"asset_id": "AST-2026-000137", "anchor_id": "AST-2026-000137#s3.p1.c1"}}
], "counts": {"candidates": 1, "rejected": 0}}
```

> 注意 `tail.label` 是「幽门螺杆菌呼气」而不是「幽门螺杆菌呼气试验」——`TAIL_SUFFIX` 会剥掉「检查/检测/试验」后缀，再靠 `expand()` 扩回最长已知实体。这是实现细节，**契约只保证 `tail.id` 可用**，下游别对 `label` 做字符串匹配。

---

### 2.5 `onto_commit` — 确认 diff 并发布新本体版本

```python
onto_commit(diff_id: str, approve_all: bool = True,
            approve_ids: list[str] = None,
            version: str = "", note: str = "") -> dict
```

**入参**

| 名 | 类型 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `diff_id` | str | 是 | — | `onto_propose` 的产出 |
| `approve_all` | bool | 否 | true | true 全收；false 时按 `approve_ids` 过滤 |
| `approve_ids` | list[str] | 否 | null | **按 `provenance.anchor_id` 匹配**，不是按候选下标 |
| `version` | str | 否 | `""` | 留空自动 `_bump()` 上一版 |
| `note` | str | 否 | `""` | 留空写 `"from <diff_id>"` |

**出参**

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `ok` | bool | |
| `diff_id` | str | 原样回传 |
| `version` | str | 发布后的版本号 |
| `added` | int | 真正新增的三元组数（重复的只更新 confidence，不计入） |
| `snapshot` | object | 见下 |
| `previous` | str \| null | 上一版版本号 |

`snapshot`：

```json
{
  "version": "v1.0",
  "triple_count": 17,
  "manifest_hash": "49c493fd8f91b0d3",
  "snapshot_path": "agent/mcp-server/data/ontology_v1.0.jsonl",
  "created_at": "2026-10-25T17:23:47+08:00"
}
```

`manifest_hash` = 快照文件 sha256 的前 16 位，用于答辩现场验证「本体没被偷偷改过」。

**真实请求 / 响应**

```json
// 请求
{"diff_id": "DF-c1fb5d64", "version": "v1.0", "note": "首个抽取版本"}
// 响应
{"ok": true, "diff_id": "DF-c1fb5d64", "version": "v1.0", "added": 0,
 "snapshot": {"version": "v1.0", "triple_count": 17, "manifest_hash": "49c493fd8f91b0d3",
              "snapshot_path": "E:\\deepseek-data\\medpal\\agent\\mcp-server\\data\\ontology_v1.0.jsonl",
              "created_at": "2026-10-25T17:23:47+08:00"},
 "previous": "v0.9"}
```

**错误**

```json
{"ok": false, "reason": "diff_not_found", "hint": "先调 onto_propose 生成 diff", "diff_id": "DF-nonexist"}
```

---

### 2.6 `std_align` — 对齐到 ICD-10 / 临床路径条目

```python
std_align(entity_text: str = "", triple_id: str = "") -> dict
```

**入参**（二选一，`triple_id` 优先）

| 名 | 类型 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `entity_text` | str | 否 | `""` | 自由文本实体 |
| `triple_id` | str | 否 | `""` | 给三元组号，先查已存 `standard_json`，有则直返 `source:"stored"` |

**出参**

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `ok` | bool | |
| `input` | str | 回显（走 `triple_id` 分支时可能缺省） |
| `aligned` | bool | 成功恒为 `true`；走 `triple_id` 且有已存 `standard_json` 时改出 `standard` + `source:"stored"` |
| `scheme` | str | `ICD-10` |
| `code` | str | 编码，如 `R10.1` |
| `match` | str | `exact`（`alias.surface` 完全相等）\| `contains`（`? LIKE '%surface%'` 命中，取最长 surface）——**只有这两个值**，无 `alias` / `fuzzy` |
| `confidence` | float | 取自 `alias` 表该行 |
| `entity_type` | str | `Disease` \| `Symptom` \| `Exam` \| `Drug` \| `Finding` \| `Department` |

**真实请求 / 响应**

```json
// 请求
{"entity_text": "上腹部痛"}
// 响应
{"ok": true, "input": "上腹部痛", "aligned": true, "scheme": "ICD-10",
 "code": "R10.1", "match": "exact", "entity_type": "Symptom", "confidence": 0.95}
// contains 分支（自由文本里含已知 surface）
{"ok": true, "input": "上腹部痛三天", "aligned": true, "scheme": "ICD-10",
 "code": "R10.1", "match": "contains", "entity_type": "Symptom", "confidence": 0.95}
// triple_id 分支且已存 standard_json
{"ok": true, "triple_id": "T-d2e6d769", "aligned": true,
 "standard": {"scheme": "ICD-10", "code": "R10.1"}, "source": "stored"}
```

**错误**

```json
{"ok": false, "reason": "unmapped", "hint": "加入待对齐队列，人工补 alias 表后重跑", "input": "张三的偏方"}
{"ok": false, "reason": "empty_input", "hint": "传入 entity_text 或 triple_id"}
{"ok": false, "reason": "triple_not_found", "hint": "检查 triple_id"}
```

---

### 2.7 `trace_write` — 写决策链 + 生成报告 + 算溯源完整率

```python
trace_write(question: str, steps: list[dict], agent_version: str = "v1.0",
            elapsed_ms: int = 0, gaps: list[str] = None) -> dict
```

**入参**

| 名 | 类型 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `question` | str | 是 | — | 用户原始问题 |
| `steps` | list[dict] | 是 | — | 至少 1 步，见下 |
| `agent_version` | str | 否 | `v1.0` | 智能体版本 |
| `elapsed_ms` | int | 否 | 0 | 端到端耗时，进报告 |
| `gaps` | list[str] | 否 | null | 已知缺口，进报告「缺口」小节 |

`steps[]` 项：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `i` | int | 是 | 步号，从 1 起 |
| `op` | str | 是 | 操作名：工具名，或 `entity_extract` / `conclude` / `conflict_check` |
| `in` | list | 是 | 输入 |
| `out` | list \| str | 是 | 输出 |
| `evidence` | list[str] | 是 | `T-xxx` 或 `AST-...#锚点`；可为空数组，但那一步算无证据 |

**出参**

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `ok` | bool | |
| `trace_id` | str | |
| `version` | str | 记录时的本体版本 |
| `report_path` | str | Markdown 报告落盘路径 |
| `evidence_count` | int | 去重后的证据条目数 |
| `trace_completeness` | float | 溯源完整率 |
| `unresolved` | list[str] | 解析不到的证据串 |

**溯源完整率定义**：`1 - len(unresolved) / len(cited)`；`cited` 为空时记 `1.0`（`store.py:503-570`）。这是 R4 的核心量化指标，答辩必讲。

**真实请求 / 响应**

```json
// 请求
{"question": "上腹隐痛的患者应去哪个科，需要做哪些检查？",
 "steps": [
   {"i": 1, "op": "kg_query", "in": ["上腹隐痛"], "out": ["SYM-EPI", "K27", "DEP-GI"],
    "evidence": ["T-d331cf32", "AST-2026-000137#s2.p1.c3"]},
   {"i": 2, "op": "std_align", "in": ["消化性溃疡"], "out": ["ICD-10 K27"],
    "evidence": ["T-b5d99245"]},
   {"i": 3, "op": "conclude", "in": ["K27"], "out": "消化内科", "evidence": []}
 ],
 "agent_version": "v1.0", "elapsed_ms": 1240, "gaps": ["未覆盖儿童剂量"]}

// 响应
{"ok": true, "trace_id": "TR-20261025-1ABA", "version": "v0.9",
 "report_path": "agent/mcp-server/reports/TR-20261025-1ABA.md",
 "evidence_count": 3, "trace_completeness": 1.0, "unresolved": []}
```

**生成的报告**（`reports/TR-20261025-1ABA.md` 实际内容，节选）：

```markdown
# 决策链报告 TR-20261025-1ABA

- 问题：上腹隐痛的患者应去哪个科，需要做哪些检查？
- 智能体版本：v1.0
- 本体版本：v0.9
- 生成时间：2026-10-25T17:24:04+08:00
- 证据数：3
- 溯源完整率：1.0

## 决策链

| # | 操作 | 输入 | 输出 | 证据 |
| --- | --- | --- | --- | --- |
| 1 | kg_query | ['上腹隐痛'] | ['SYM-EPI', 'K27', 'DEP-GI'] | T-d331cf32, AST-2026-000137#s2.p1.c3 |
| 2 | std_align | ['消化性溃疡'] | ['ICD-10 K27'] | T-b5d99245 |
| 3 | conclude | ['K27'] | 消化内科 | — |

## 证据清单

- T-d331cf32 ✅
- AST-2026-000137#s2.p1.c3 ✅
- T-b5d99245 ✅

## 缺口

- 未覆盖儿童剂量
```

**错误**

```json
{"ok": false, "reason": "empty_steps", "hint": "至少一步"}
```

---

### 2.8 `skill_export` — trace 导出成 Skill 模板草稿

```python
skill_export(trace_id: str, name: str = "") -> dict
```

**入参**

| 名 | 类型 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `trace_id` | str | 是 | — | |
| `name` | str | 否 | `""` | 留空生成 `auto-<trace_id 小写>` |

**出参**：`ok`、`trace_id`、`skill_md`（完整 SKILL.md 文本）、`tools`（trace 里用到的工具名，已排除 `entity_extract` / `conclude` / `conflict_check`）。

**真实请求 / 响应**

```json
// 请求
{"trace_id": "TR-20261025-1ABA", "name": "digestive-triage"}

// 响应
{
  "ok": true,
  "trace_id": "TR-20261025-1ABA",
  "skill_md": "---\nname: digestive-triage\ndescription: 由 trace TR-20261025-1ABA 自动导出，覆盖步骤 3 步\nallowed-tools: [kg_query, std_align]\ntags: [auto-exported, medical]\n---\n\n## 何时用\n问题形态与「上腹隐痛的患者应去哪个科，需要做哪些检查？」相近时。\n\n## 步骤\n1. kg_query -> ['SYM-EPI', 'K27', 'DEP-GI']\n2. std_align -> ['ICD-10 K27']\n3. conclude -> 消化内科\n\n## 禁止\n- 引用无 anchor_id 的内容\n- 给出药品剂量",
  "tools": ["kg_query", "std_align"]
}
```

`skill_md` 展开后：

```markdown
---
name: digestive-triage
description: 由 trace TR-20261025-1ABA 自动导出，覆盖步骤 3 步
allowed-tools: [kg_query, std_align]
tags: [auto-exported, medical]
---

## 何时用
问题形态与「上腹隐痛的患者应去哪个科，需要做哪些检查？」相近时。

## 步骤
1. kg_query -> ['SYM-EPI', 'K27', 'DEP-GI']
2. std_align -> ['ICD-10 K27']
3. conclude -> 消化内科

## 禁止
- 引用无 anchor_id 的内容
- 给出药品剂量
```

> frontmatter 字段（`name` / `description` / `allowed-tools` / `tags`）与 Nexent 技能规范一致，但**导出的是草稿**，直接丢弃会丢掉「何时用」和「禁止」两节的语义。进 `agent/skills/` 前需人工改写。

**错误**

```json
{"ok": false, "reason": "trace_not_found", "hint": "检查 trace_id"}
```

---

### 2.9 `kb_search` — 知识库检索透传（辅助）

```python
kb_search(query: str, top_k: int = 5, mode: str = "hybrid") -> dict
```

| 名 | 类型 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `query` | str | 是 | — | |
| `top_k` | int | 否 | 5 | |
| `mode` | str | 否 | `hybrid` | `hybrid` \| `vector` \| `keyword` |

**当前状态：stub。** 未设 `KB_ENDPOINT` 时返回配置提示；设了也只回空 `results`（`server.py:449-461`）。真正的检索由 Nexent 的 `search-knowledge-base` 技能承担，**这个工具是给不接 Nexent 的纯 MCP 场景留的口子**。

```json
// 响应（未配置）
{"ok": false, "reason": "kb_not_configured",
 "hint": "设置 KB_ENDPOINT 后由 Nexent 混合检索承担；否则直接用平台 search-knowledge-base 技能",
 "query": "消化性溃疡 诊断依据"}
```

---

### 2.10 `health` — 健康检查（辅助）

```python
health() -> dict
```

```json
{"ok": true, "server_version": "0.1.0", "triples": 17, "assets": 1,
 "ontology_version": "v0.9", "db": "agent/mcp-server/data/medpal.db"}
```

`db` 是**服务端**的库路径，用于确认挂载时连的是哪个库——Nexent 挂不上时第一个该看的字段。

---

## 3. 错误码总表

失败一律 `{"ok": false, "reason": <下表>, "hint": ...}`。

| # | reason | 含义 | 触发工具 | 定义位置 | 调用方该做什么 |
| --- | --- | --- | --- | --- | --- |
| 1 | `file_not_found` | 路径不存在 | `ingest_asset` | `server.py:74` | 检查路径 |
| 2 | `no_parser` | 扩展名无解析器 | `ingest_asset` | `server.py:77` | 换格式或注册 Parser |
| 3 | `parser_unavailable` | 解析器依赖缺失/自报错 | `ingest_asset` | `server.py:79` | 装依赖（pymupdf / openpyxl） |
| 4 | `asset_not_found` | 资产号不存在 | `get_asset_card` | `server.py:126` | 先 `ingest_asset` |
| 5 | `diff_not_found` | diff 号不存在 | `onto_commit` | `server.py:316` | 先 `onto_propose` |
| 6 | `triple_not_found` | 三元组号不存在 | `std_align` | `server.py:360` | 检查 id |
| 7 | `empty_input` | 必填入参全空 | `std_align` | `server.py:366` | 传 `entity_text` 或 `triple_id` |
| 8 | `unmapped` | 对齐不上 | `std_align` | `server.py:369` | 进待对齐队列，补 alias |
| 9 | `empty_steps` | 决策链无步骤 | `trace_write` | `server.py:399` | 至少一步 |
| 10 | `trace_not_found` | trace 号不存在 | `skill_export` | `server.py:414` | 检查 `trace_id` |
| 11 | `kb_not_configured` | 未设 `KB_ENDPOINT` | `kb_search` | `server.py:455` | 配 env，或改用 Nexent 技能 |
| 12 | `no_seed` | 种子实体为空 | `kg_query` | `store.py:247` | 先做实体归一 |
| 13 | `no_path` | 有种子但连不上任何路径 | `kg_query` | `store.py:346` | 看 `unresolved` 换词重查 |

**新增错误码流程**：先改本文 §3 → 再改代码 → 再让 T6 的 client 断言。顺序不能反。

---

## 4. 版本演进规则

### 4.1 三套版本号不混用

| 号 | 指什么 | 谁改 | 例 |
| --- | --- | --- | --- |
| `server_version` | 代码契约版本 | T1 | `0.1.0` |
| `schema v0` / `v1` | 实体与关系的**结构** | T1 裁决 + T4 执行 | `v0` |
| 本体快照 `v0.9` / `v1.0` / `v1.1` | **数据** | T4 | `v0.9` → `v1.0` |

差分报告写「v0.9→v1.0」，不写「v0→v1」。

### 4.2 什么改动升什么号

| 改动性质 | 版本动作 | 需要谁同意 |
| --- | --- | --- |
| 加工具、删工具、改入参名 / 类型 / 必填性 | `server_version` 升**次**号；契约文档同步改 | **T1 裁决**，提前一天公告 |
| 加可选入参（有默认值）、加出参字段 | `server_version` 升次号；向后兼容，可当天改 | T1 知会 |
| 改出参字段名、改错误码文案、改 `reason` 取值 | **破坏性**，必须同步改 §3 + T6 的断言 | T1 裁决 + 全员确认 |
| 改实体类型 / 关系类型集合 | `schema` 升主号（`v0`→`v1`）；旧数据需迁移脚本 | T1 裁决 |
| 只加三元组数据 | 本体快照升次号（`v1.0`→`v1.1`） | T4 自主 |
| 改 `trace.json` 结构 | 走 `agent/docs/trace-schema.md`（交付物 1.2） | T1 |

### 4.3 冻结与解冻

- 本文状态「冻结候选」→ T6 照本文写出可运行的 client 并通过 → 状态改「**已冻结 v1**」，此后只增不改；
- 冻结后任何人发现文档与代码不一致，**先提 issue 给 T1**，不许自己改代码绕过；
- 每周日 24:00 PR 合并前，T1 用 `python tests/test_mcp_client.py` 复核一次工具清单。

---

## 5. 下游怎么验（T6 的硬门槛）

按本文写一个 MCP client，跑通下面 5 条就算过：

```bash
# 1) 工具清单是 10 个，名字与 §2 一字不差
cd agent && python tests/test_mcp_client.py
#    期望最后一行：MCP CLIENT OK

# 2) health 能读库
#    期望 triples >= 12，且 db 字段指向你要的那个库

# 3) kg_query 两跳命中 K27
#    期望 paths 非空，且某个 path 的 nodes 含 "K27"

# 4) std_align 编码正确
#    期望 {"code": "R10.1", "match": "exact", "ok": true}

# 5) 错误信封形状正确（挑一个失败分支）
#    期望 ok=false 且同时有 reason 和 hint
```

HTTP 方式另跑下面两条（`MCP_TRANSPORT=streamable-http` 起服务；已实测通过）：

```bash
# Git Bash / Linux
MCP_TRANSPORT=streamable-http python mcp-server/server.py &
cd agent && python tests/test_http_client.py     # 期望最后一行：HTTP TRANSPORT OK

# PowerShell
$env:MCP_TRANSPORT="streamable-http"; python mcp-server/server.py
python tests/test_http_client.py
```

> 若报 `502 Bad Gateway` 而 `netstat -ano | findstr :8090` 确实有 LISTENING，那是系统代理拦了回环，不是服务挂了；`tests/test_http_client.py` 已内置 `trust_env=False` 处理，见 §0.2。

**写不出来算 1.1 没过**——这是任务卡里写死的验收条款，不是我加的。

---

## 附录 A：契约与代码的对齐核查表

| 检查项 | 结论 |
| --- | --- |
| 10 个工具名 | ✅ 与 `EXPECTED`（`tests/test_mcp_client.py:20-31`）一致 |
| 13 个错误码 | ✅ 逐个对应到行号，见 §3 |
| 入参签名 | ✅ 由 `inspect.signature()` 实测导出（含默认值） |
| 出参字段 | ✅ 全部真实调用产出，非手写 |
| 锚点四种格式 | ✅ 由 `parsers.py` 四类 Parser 实测 |
| **未覆盖**：`treated_by` / `subclass_of` 无抽取器 | ⚠️ 已知缺口，见 §1.4 |
| **未覆盖**：`too_short` 阈值 12 vs 方案 30 | ⚠️ 待裁决，见 §2.4 |
| **未覆盖**：`kb_search` 是 stub | ⚠️ 见 §2.9 |
| **未覆盖**：`store.snapshot()` 写死 `DATA_DIR` | ⚠️ 测试会污染主库，见 §1.5 |

## 附录 B：取证脚本

所有示例响应由以下脚本真实跑出，可复现：

- `tmp/probe_contract.py` — health / get_asset_card / kg_query / std_align / onto_propose / trace_write / skill_export + 6 个错误分支
- `tmp/probe_contract2.py` — ingest_asset / onto_commit / kb_search + 3 个错误分支
- `tmp/probe_contract3.py` — 用 `inspect.signature()` 导出全部签名，并逐个真实调用
- `tmp/probe_contract4.py` — onto_propose 完整 `rejected` 明细 + skill_export 的 `skill_md` 原文

跑法（用库副本，不动主库）：

```bash
cd agent/mcp-server && PYTHONIOENCODING=utf-8 python ../../tmp/probe_contract3.py
```
