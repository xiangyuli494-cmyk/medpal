# MedPal-Cog trace.json Schema v1

> 交付物 1.2 · T1 xiangyuli494-cmyk · 2026-10-25 · 状态：**冻结候选**
> 适用对象：T2 的 trace 生产、T3 的静态可视化、T4 的模板导出、T6 的溯源完整率检查
> 唯一事实来源：`agent/mcp-server/store.py`（`write_trace` / `get_trace` / `_ref_str` / `_evidence_exists`）、`agent/mcp-server/server.py`（`trace_write` / `skill_export`）、`agent/skeleton.py`
> 本文与代码冲突时以代码为准，并**改文档**；本文与 `agent/tools/trace.schema.json` 冲突时以 Schema 文件为准（它是可执行的）。

---

## 0. 这份文档为什么必须存在

决赛要求 R4 是「跨文档多跳推理 + 决策链路可溯源」。评委看的不是你说能溯源，是**指着报告上某一行问「这条依据在哪」，你能不能当场点回原文**。

现在仓库里关于「决策链长什么样」有三套说法，互相对不上：

| 来源 | 形状 | 问题 |
| --- | --- | --- |
| `agent/skeleton.py` 落盘的 `tmp/trace.json` | `schema: "walking-skeleton/1"`，step 用 `step/op/detail/evidence/ref` | 字段名自成一派，`ref` 存的是层标签不是引用 |
| 方案 `docs/赛题3-方案-v1.2.md:452-476` 8.1 节示例 | step 用 `i/op/in/out/evidence`，但第 3 步用 `query` 而不是 `in` | 示例本身内部不一致 |
| `store.write_trace` 实际落库形态 | step 用 `i/op/in/out/evidence`，其余字段**原样透传不校验** | 没有约束，垃圾数据也能写进去 |

三套并存的结果已经发生了：`agent/mcp-server/data/medpal.db` 里 31 条 trace，其中 17 条是探测脚本写进去的畸形数据（缺 `i`、`evidence` 传字符串、`i` 乱序、`op` 是随便编的），全部 `ok: true`，全部生成了"看起来正常"的报告。T3 的 `trace.html` 一旦上线，第一屏就会渲染出 `| None | kg_query |  |  | — |` 这样的行。

所以 v1 的职责只有一句话：**冻结一套唯一口径，并配一台机器替所有人执行它。**

---

## 1. 顶层结构

真实样例（`agent/tests/fixtures/trace_v1_example.json`，由 `tools/build_trace_fixture.py` 真跑生成，非手抄）：

```json
{
  "schema": "medpal-trace/1",
  "trace_id": "TR-20261026-043F",
  "question": "反复上腹隐痛3个月，夜间加重，进食后缓解，近两周服用布洛芬",
  "agent_version": "offline-baseline",
  "ontology_version": "v0.9",
  "created_at": "2026-10-26T00:04:00+08:00",
  "elapsed_ms": 13,
  "steps": [
    {"i": 1, "op": "entity_extract", "out": ["上腹隐痛", "布洛芬"], "evidence": []},
    {"i": 2, "op": "std_align", "out": ["DRUG-IBU", "SYM-EPI"], "evidence": []},
    {"i": 3, "op": "kg_query", "in": ["上腹隐痛", "布洛芬"],
     "out": ["K27", "ICD10-K27", "EX-HP-BT", "DEP-GI"],
     "confidence": 0.89,
     "evidence": ["T-d331cf32", "T-b5d99245", "AST-2026-000137#s2.p1.c3", "AST-2026-000137#s3.p1.c1"]},
    {"i": 4, "op": "conflict_check", "in": ["布洛芬", "K27"], "out": ["布洛芬"], "evidence": []},
    {"i": 5, "op": "conclude", "ref": "CONCLUDE",
     "out": {"dept": "消化内科", "conf": 0.9, "exams": ["幽门螺杆菌呼气试验", "胃镜检查"]},
     "evidence": ["AST-2026-000137#s1.h", "AST-2026-000137#s2.p1.c2", "AST-2026-000137#s3.p1.c2"]}
  ],
  "gaps": [],
  "trace_completeness": 1.0,
  "unresolved": [],
  "sources": ["AST-2026-000137"]
}
```

字段表：

| 字段 | 类型 | 必填 | 谁产生 | 说明 |
| --- | --- | --- | --- | --- |
| `schema` | const `"medpal-trace/1"` | ✅ | 生产者 | 版本闸门。不写就是旧方言，校验器直接拒 |
| `trace_id` | `TR-YYYYMMDD-XXXX` | ✅ | `store.py:504` | 后四位大写十六进制。**别手填** |
| `question` | string | ✅ | 调用方 | 原始问题，不改写 |
| `agent_version` | string | ✅ | 调用方 | 离线基线写 `offline-baseline`，接 Nexent 后写实际版本 |
| `ontology_version` | `vX.Y` | ✅ | `current_version(conn)` | 写入时刻的本体版本，见契约 §4.1 |
| `created_at` | ISO8601 带 `+08:00` | 建议 | `now()` | 报告头部 |
| `elapsed_ms` | int ≥ 0 | 建议 | 调用方 | 端到端耗时 |
| `steps` | step[] ≥ 1 | ✅ | 调用方 | 见 §2 |
| `sources` | `AST-*`[] | 派生 | 后端反推 | **不接受手填**，见 §5 |
| `conclusion` | object | 可选 | 调用方 | 顶层结论摘要，字段随业务走 |
| `gaps` | string[] | ✅ | 调用方 | 缺口清单，人话。空也给 `[]`，不给 `null` |
| `trace_completeness` | number 0–1 | ✅ | `store.py:534` | 溯源完整率，见 §6 |
| `unresolved` | string[] | 派生 | `store.py:533` | 查不到落点的引用，给 T6 用 |

---

## 2. step 结构

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `i` | int ≥ 1 | ✅ | 步序，**严格递增**。报告第一列 |
| `op` | 枚举 | ✅ | 操作名，见 §3.1。`op` 是"做了什么"，不是"用了哪个工具" |
| `in` | string[] | 视 op | 本步输入。**必须是数组**，不是 JSON 字符串 |
| `out` | array \| object \| string | 建议 | 本步输出。`conclude` 一般是对象 |
| `evidence` | string[] | ✅ | 证据引用，见 §4。空数组合法，`null`/字符串非法 |
| `ref` | `PARSE`/`EVIDENCE`/`STORE`/`TRAVERSE`/`CONCLUDE` | 可选 | 粗粒度层标签，与 `op` 有映射（§3.2）。v1 起可省 |
| `confidence` | number 0–1 | 可选 | 本步置信度，见 §3.3 |
| `detail` | string | 可选 | 人话补充，进报告"操作"列 |

`additionalProperties: true`——不禁止扩展字段（`store.py:511` 整包 `json.dumps`，加字段不会被丢），但**扩展字段不会被报告渲染**，见 §7.1。

---

## 3. 三个最容易含糊的字段

### 3.1 `op` 词表（冻结）

| op | 语义 | 典型 evidence |
| --- | --- | --- |
| `ingest` | 资产入库 | `["AST-..."]` |
| `parse` | 解析原文成 blocks/anchors | anchor |
| `entity_extract` | 抽实体 | `[]`（抽的是问题不是文档） |
| `std_align` | 对齐 ICD-10 | `[]` 或 anchor |
| `align_evidence` | 本体三元组对齐、断链检查 | anchor |
| `kg_query` | 图遍历取路径 | `T-*` + anchor |
| `reason_2hop` | **遗留名**，等价 `kg_query`，只出现在旧方言 | — |
| `retrieve` | 检索原文片段 | anchor |
| `conflict_check` | 冲突检测 | `[]` 或 `T-*` |
| `conclude` | 出结论 | anchor + `T-*` |
| `skill_export` | 导出模板 | `[]` |

新增 `op` 必须升 schema 次版本并同步本表——因为 T3 的图例、T4 的步骤段导出都按这张表分颜色/分段。

### 3.2 `ref` 与 `op` 的关系

`ref` 是骨架期遗留的**层标签**（5 个值），`op` 是动作（11 个值）。两者是粗/细关系，映射表在 `tools/validate_trace.py` 的 `REF_BY_OP`。

v1 起 **`ref` 可省略**：省了由 `op` 推导，写了必须与映射表一致。理由：两处表达同一件事，早晚会写出"`op: kg_query` 但 `ref: PARSE`"这种自相矛盾的记录，而报告只渲染 `op`，矛盾根本不会暴露。校验器现在会在 `ref` 与 `op` 不符时报错。

### 3.3 `confidence` 三个层级，别混着用

代码里"置信度"出现在三个地方，意义不同：

| 层级 | 来源 | 取值 | 落点 |
| --- | --- | --- | --- |
| 边级 | `triple.confidence` | 实测 0.7×1 / 0.8×5 / 0.9×8 / 1.0×3，min 0.7 max 0.99 avg 0.8782 | `kg_query` 的 `steps[].score` 内部 |
| 路径级 | `kg_query` 的 `score` = 该路径各边置信度**均值** | 实测 `hops=3, edges=[0.8,0.88,0.99] → 0.89` | 建议写进 step 的 `confidence` |
| 结论级 | `eval/run_eval.py:179` `conf = min(0.9, 0.4 + 0.1*len(paths))`；`std_align` 的 `confidence = 0.95` | 0.4–0.9 / 0.95 | `conclude` 的 `out.conf` |

**规矩**：step 的 `confidence` 填"这一步的产出有多可信"，路径级用均值，结论级放 `out.conf`，不要把结论置信度提到顶层假装是"整条 trace 的置信度"——trace 没有单一置信度，它是一条链，链的强度取决于最弱的一跳。

---

## 4. `evidence`：v1 的全部约束都在这里

**允许三种形态，除此之外一律非法：**

| 形态 | 例 | `_evidence_exists` 怎么查（`store.py:471-483`） |
| --- | --- | --- |
| 三元组 id | `T-d331cf32` | 查 `triple.triple_id` |
| 资产锚点 | `AST-2026-000137#s2.p1.c3` | 按 `#` 切出 asset_id，在 `asset.anchors_json` 里**精确匹配整个 ref** |
| 裸资产 id | `AST-2026-000137` | 查 `asset.asset_id` |

### 4.1 `evidence` 必须是数组，不能是字符串

这是**已经发生过的真实事故**，不是假想：

```python
store.write_trace(conn, "...", [{"i": 1, "op": "kg_query", "evidence": "T-d2e6d769"}], ...)
# 实际返回：evidence_count=8, trace_completeness=0.0
# unresolved = ['T', '-', 'd', '2', 'e', '6', '7', '9']
```

`store.py:527` 是 `for e in s.get("evidence", [])`——传字符串就按字符遍历。8 个字符变成 8 条"证据"，全部查不到，完整率掉到 0，**报告照写、接口照返回 ok**。

所以：**write_trace 不做类型校验是已知缺陷，schema 在文档层和校验器层双重卡死它**。

### 4.2 字典引用必须先摊平

`kg_query` 返回的 `provenance` 是 `{"asset_id": "...", "anchor_id": "..."}` 结构，直接塞进 `evidence` 会变成字符串化的字典。必须走 `_ref_str`（`store.py:486-500`）：

| 输入 | 输出 |
| --- | --- |
| `{"triple_id": "T-d331cf32"}` | `"T-d331cf32"`（**优先于 anchor**） |
| `{"asset_id": "AST-2026-000137", "anchor_id": "#s2.p1.c3"}` | `"AST-2026-000137#s2.p1.c3"`（`#` 被 `split("#")[-1]` 剥掉再拼） |
| `{"asset_id": "AST-2026-000137", "anchor_id": "s1.h"}` | `"AST-2026-000137#s1.h"` |
| `{"anchor_id": "#s2.p1.c3"}`（无 asset_id） | `"#s2.p1.c3"` ← **必然 unresolved**，缺资产前缀就没有落点 |
| `{}` | `"{}"` ← 静默垃圾 |
| `None` | `"None"` ← 静默垃圾 |

**硬规矩**：往 `evidence` 里放字典前先 `_ref_str()`，且必须有 `triple_id` 或（`asset_id` + `anchor_id`）之一，否则宁可不放。

### 4.3 证据会重复，去重口径在 `cited`

实测 `TR-20261025-82B2`：step 3 的 `evidence` 有 39 条，去重后 6 条；全 trace 原始 45 条，去重后 6 条。

`store.py:526-530` 用 `cited` 按**首次出现顺序**去重，`evidence_count` 与 `trace_completeness` 都按去重后算。但**报告表格里渲染的是未去重的原始数组**（`store.py:560`），所以同一行会看到 `AST-...#s4.p1.c2` 连刷十几遍——这是可读性问题，不是数据错误。v1 不改口径（改了会动到已有 14 条 trace 的完整率），但在文档里写清楚：**看完整率看 `trace_completeness`，看证据列表看"证据清单"段。**

---

## 5. `sources`：来源资产必须派生，不能手填

R4 要求"跨文档"。当下 `agent/mcp-server/data/medpal.db` 里只有 **1 份资产** `AST-2026-000137`，14 条 trace 全是单文档——**"跨文档"目前演示不出来**，这是 T5 要供数据的地方，先记在这。

派生规则（`tools/validate_trace.py:derive_sources`）：

- `AST-xxx#anchor` → 取 `#` 前缀
- `T-<8hex>` → 查 `triple.asset_id`（**必须连库**，不连库算不出，宁可缺也不猜）
- 裸 `AST-xxx` → 自身

去重后 `sorted()`。实测 14 条 trace 里 11 条 `sources = ["AST-2026-000137"]`，3 条为空——那 3 条是拒答题（`孩子发烧39度`、`心电图ST段抬高`、`拉肚子三天还发烧`），证据数组本来就是空，属于正确行为。

**为什么禁止手填**：手填的 `sources` 会和 `evidence` 脱钩。评委随手点一条证据跳到 `AST-2026-000155`，而 `sources` 里没这份资产——溯源当场崩。派生的值永远自洽。

---

## 6. 溯源完整率：两个口径已经在打架，必须裁一次

| 出处 | 定义 | 分母 |
| --- | --- | --- |
| `store.py:534` 实现 | `round(1 - len(unresolved)/len(cited), 3)`，`cited` 为空时 **1.0** | 去重后的证据条目 |
| 方案 `docs/赛题3-方案-v1.2.md:496` 指标表 | 「有 anchor_id 且能点回原文的**结论**占比 ≥ 95%」 | 结论条数 |

同一份 trace 能算出两个数：`TR-20261025-82B2` 按代码是 `1.0`，按方案口径要数"结论里有多少条带 anchor"。

**v1 裁决：以代码口径为准，因为它是能自动化的那个。**

- 代码口径可以从 `steps_json` 完全重算，T6 的 CI 能每天跑；
- 方案口径需要先把"哪一句算结论"人工标注出来，评审时反而变成弱点（"你这 95% 是谁标的"）；
- 代码口径更严格：它要求**每一条**引用都落得到原文，不只是结论那几条。

留给评委会的话术：「我们报告的溯源完整率是**证据级**的，不是结论级——每一条引用都要能点回原文的 anchor，任一条落不了地就扣分。这比只统计结论更严。」

**`cited` 为空记 1.0 这条要留着**，但要理解它的含义：拒答题不引用证据，就不存在"引用落不了地"，所以不算不完整。代价是"什么都不引用"能拿满分——所以报告必须同时显示**证据数**（`store.py:545` 已经这么做了：`证据数：0（无引用，拒答类结论）`），单看完整率会被糊弄。

---

## 7. 已知缺口（写进文档，不让下游自己撞）

### 7.1 `confidence` 存得进、渲染不出

`store.py:511` 把 `steps` 整包 `json.dumps`，所以 `confidence`/`ref`/`detail` 写进去能存能读。但报告渲染（`store.py:553-565`）只取 `i`/`op`/`in`/`out`/`evidence` 五列，**`confidence` 根本不进报告**。

后果：`conclude` 步的 `out.conf` 会在"输出"列以 `{'conf': 0.9, ...}` 的形式露出来（因为 `out` 整包 `str()`），而 step 级 `confidence` 彻底消失。

**处置**：v1 接受现状（不改渲染器，避免动到 14 条已有 trace 的报告格式）。T3 的 `trace.html` 直接读 JSON，可以正常显示 `confidence`。**给 T2 的待办：如果要在 Markdown 报告里看到它，改 `store.py:553-565` 加一列，且这一列要能容忍缺字段（渲染 `—`）。**

### 7.2 `skill_export` 不过滤未知 `op`

实测：`steps` 里放一个 `op: "不存在的op"`，导出的 `SKILL.md` 里 `allowed-tools: [kg_query, 不存在的op, retrieve]`——**原样写进去了**。

`server.py:416-421` 只做了排除（`entity_extract`/`conclude`/`conflict_check` 不进 allowed-tools），没有白名单。所以 schema 里 `op` 的枚举是唯一防线。

**给 T4 的提醒**：模板导出用到的 `op` 必须过 schema 枚举，别从自由字段里捞。

### 7.3 步序不排序、不校验

`write_trace` 原样存。实测传 `i` 为 `(3, 1, 1)` 的数组，回读仍是 `(3, 1, 1)`，报告按传入顺序渲染成 3/1/1 三行。

v1 要求**生产者保证严格递增**，校验器报错。不改 `write_trace` 自动排序——因为排序会掩盖生产者的 bug，而这类 bug 在"多跳并发抓取后合并"时最容易出现。

### 7.4 缺字段不报错，只渲染空

实测：`{"op": "kg_query", "evidence": []}`（无 `i`/`in`/`out`）→ `ok: true`，报告出 `| None | kg_query |  |  | — |`。

校验器把 `i`/`op`/`evidence` 定为 required，这类记录一律拒。

---

## 8. 怎么验：一台机器替所有人执行

### 8.1 命令行

```bash
cd agent
export PYTHONIOENCODING=utf-8        # Windows 不加必乱码

# 单份
python tools/validate_trace.py tests/fixtures/trace_v1_example.json

# 库里最近 N 条真实 trace
python tools/validate_trace.py --db mcp-server/data/medpal.db --limit 20

# CI 门禁（只输出不合格项，退出码 0/1）
python tools/validate_trace.py --db mcp-server/data/medpal.db --limit 50 --quiet

# 旧方言迁移
python tools/validate_trace.py ../tmp/trace.json --migrate
```

### 8.2 实测基线（2026-10-26 00:05）

```
✅ 14/14 合格   （库里 14 条 offline-baseline trace，全部 sources 已派生）
❌ 17/17 已清理 （探测脚本写进去的畸形 trace，已从库里删除）
```

清理前的样子，用来对照：

```
❌ TR-20261025-389C  - steps/0: 'i' is a required property
❌ TR-20261025-3F35  - steps/1/evidence/1: {...} is not of type 'string'
❌ TR-20261025-BFE4  - steps/2/op: 'dup' is not one of [...]
                     - steps: i 必须严格递增，实际 [3, 1, 1]
❌ TR-20261025-BC93  - steps/0/evidence: 'T-0f5bfa1d' is not of type 'array'
❌ TR-20261025-8587  - steps/0/i: 0 is less than the minimum of 1
```

### 8.3 测试

```bash
python -m pytest tests/test_trace_schema.py -q      # 18 passed
```

覆盖 8 类已知坏输入 + 完整率公式与 `store` 一致 + 旧方言拒收与迁移 + `--db` 路径可跑。

---

## 9. 旧方言迁移（walking-skeleton/1 → medpal-trace/1）

| 旧 | 新 | 处理 |
| --- | --- | --- |
| `schema: "walking-skeleton/1"` | `"medpal-trace/1"` | 直改 |
| `step` | `i` | 改名，值不变 |
| `op: reason_2hop` | `op: kg_query` | 改名 |
| `detail` | `detail` | 保留（v1 仍认） |
| `ref: "PARSE"…` | 省略 | v1 由 `op` 推导 |
| `asset` / `ontology` / `query` | 无 | 这三个是骨架期统计块，进不了 v1 顶层（`additionalProperties: false`）；资产信息已在 `sources` |
| `conclusion` | `conclusion` | 原样搬 |
| evidence 前缀 `pathway_k27#p1` | `AST-2026-000137#p1` | 伪资产前缀按 `trace.asset.asset_id` 替换，**并在 `gaps` 留痕**（见下） |

迁移**不猜锚点**：`p1` 这种块级锚点在新资产里未必存在，强行凑一个"看起来能对上"的锚点就是造假。所以只改前缀，锚点是否真实存在交给校验器判 `unresolved`，同时在 `gaps` 里加一条：

> 骨架期有 7 条证据用文件名当资产前缀，迁移时已改挂 AST-2026-000137，锚点需按真实 blocks 重对

这条会出现在报告"缺口"段——评审看到的是"我们知道这里要重对"，而不是"我们声称对齐了"。

---

## 10. 下游各自怎么用

| 角色 | 用途 | 硬约束 |
| --- | --- | --- |
| T2 生产 | `write_trace` 前自查 `steps` | `i` 严格递增；`evidence` 是数组；字典先 `_ref_str` |
| T3 可视化 | 读 JSON 画 5 步链 | 必须容忍 `in`/`out` 缺失；`ref` 缺失时按 `op` 上色；换任意一份 trace 都要能画（任务卡 3.1 验收） |
| T4 模板导出 | `steps.op` → `allowed-tools` | `op` 必须在 §3.1 枚举内，别捞到 `不存在的op`（§7.2） |
| T6 CI | `validate_trace.py --quiet` | 退出码非 0 就红；完整率按代码口径（§6） |
| 答辩 | 报告 `证据清单` 段 | 每条带 ✅/❌；❌ 必须能解释成"这部分超出本体覆盖" |

---

## 11. 待裁决（T1 决定，组内可提异议）

1. **完整率口径**：v1 用代码口径（证据级）。若答辩要求改成方案口径（结论级），需同时改 `store.py:534` 与方案 §9.1 指标表，不能只改一处。
2. **`ref` 是否彻底删**：v1 保留可选。若 W2 结束仍无人写 `ref`，v2 删掉。
3. **报告加不加 `confidence` 列**：v1 不改渲染器（§7.1）。T2 若同意加，需同时改 `store.py:553-565` 与本文件 §7.1。

---

## 附录 A：与代码的对齐核查表

| 文档说的 | 代码位置 | 一致 |
| --- | --- | --- |
| `trace` 表 8 列 | `store.py:62-71` | ✅ |
| `trace_id` 格式 | `store.py:504` | ✅ |
| `steps` 整包序列化不校验 | `store.py:511` | ✅ |
| `cited` 按首现去重 | `store.py:526-530` | ✅ |
| 完整率公式与空引用记 1.0 | `store.py:534` | ✅ |
| 报告五列 | `store.py:553-565` | ✅ |
| 证据数带"拒答类结论"后缀 | `store.py:545` | ✅ |
| `_ref_str` 四分支 | `store.py:486-500` | ✅ |
| `_evidence_exists` 三分支 | `store.py:471-483` | ✅ |
| `get_trace` 返回 8 字段 | `store.py:581-593` | ✅ |
| `trace_write` 空 steps 报错 | `server.py:398` | ✅ |
| `skill_export` 只排除不过滤 | `server.py:416-421` | ✅（是缺口，已记 §7.2） |
| 旧方言 `SCHEMA_VERSION` | `skeleton.py:26` | ✅ |

## 附录 B：配套文件

| 文件 | 作用 |
| --- | --- |
| `agent/tools/trace.schema.json` | 机器可读 schema（JSON Schema 2020-12），唯一权威 |
| `agent/tools/validate_trace.py` | 校验 + 迁移 + 从库批量校验，`--quiet` 供 CI |
| `agent/tools/build_trace_fixture.py` | 走真实写入路径重建 fixture，保证样例可复现 |
| `agent/tests/test_trace_schema.py` | 18 条测试，卡住 8 类已知坏输入 + ref/op 一致性 + sources 派生 |
| `agent/tests/fixtures/trace_v1_example.json` | 真跑生成的合规样例 |

---

## 附录 C：v1 冻结记录

| 项 | 值 |
| --- | --- |
| 冻结时间 | 2026-10-26 00:10 +08:00 |
| 校验器实测 | 库内 14 条真实 trace **14/14 合格**；8 类已知坏输入全部被拒 |
| 测试 | `python -m pytest tests/test_trace_schema.py -q` → **18 passed** |
| 迁移实测 | `../tmp/trace.json`（walking-skeleton/1）→ 合规 v1，`p1` 伪前缀改挂 `AST-2026-000137` 并在 `gaps` 留痕 |
| 数据清理 | 删除探测脚本写入的 17 条畸形 trace 及其报告，库内只留 14 条离线基线 |
| 未关闭 | §11 三条待裁决 + §7.2 缺口（`skill_export` 不过滤未知 `op`，属 T4 侧） |
