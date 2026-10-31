# 本体 schema v0（结构冻结版）

| 项 | 值 |
| --- | --- |
| 版本 | schema **v0**（结构）／数据快照 v0.9（种子） |
| 冻结日期 | 2026-10-29 |
| 责任人 | T1 · xiangyuli494-cmyk |
| 状态 | **已冻结**。改结构要走 §11 流程，改数据不算改结构 |
| 权威性 | 实体类型、关系类型、三元组字段、命名规范、校验规则，以本文件为唯一口径。方案 §5.1 是设计意图的出处，两者冲突时以本文件为准并在 §9 登记 |
| 代码依据 | `agent/mcp-server/store.py`（表结构与读路径）、`agent/mcp-server/server.py`（写路径与抽取） |

> 这份文件的前身是 `agent/docs/赛题3-方案-v1.2.md` §5.1。§5.1 讲的是「为什么这么设计」，本文讲的是「照这个写，写成什么样算对」。T2 建图、T4 对齐、T5 建库都按本文的字段名写，不按 §5.1 的叙述性文字猜。

---

## 0 边界

**管**：三元组长什么样、6 类实体各自的命名规则、8 类关系各自允许的头尾类型、哪些字段必填、什么算重复、什么算冲突、版本号怎么加。

**不管**：怎么抽（T2 的 `agent/ontology/extract.py`）、怎么对齐 ICD-10（T4 的 `agent/ontology/align.py`）、怎么建向量库（T5）、怎么可视化（T3）。本文只规定它们交接的那一层数据形状。

---

## 1 三个号，不要混

仓库里同时存在三套版本号，混用会在答辩现场被抓：

| 号 | 形态 | 指什么 | 谁改 | 现在是多少 |
| --- | --- | --- | --- | --- |
| **schema 版本** | `v0` / `v1` | 实体与关系的**结构**：6 类实体、8 类关系、字段集 | 只能 T1 裁决后改，走 §11 | `v0`（本文冻结） |
| **本体快照版本** | `v0.9` / `v1.0` / `v1.1` | **数据**：某一次快照里有哪些三元组 | `onto_commit` 自动 +1 | `v0.9`（17 条，待审） |
| **资产 / 文档版本** | `2023 版` / `2023` | 原始文档自身的版本，存在 `asset.version_json.value` | `ingest_asset` 写入 | `2023` |

**正确说法**：

- 「schema v0 冻结，种子数据是 v0.9」——结构定了，数据还没发布
- 「差分报告 v0.9 → v1.0」——比较的是两个数据快照
- 「2023 版临床路径」——说的是来源文档

**错误说法**：「schema 从 v0 升到 v1.0」「本体从 v0 升到 v1」——把结构号和数据号混在一起。

代码事实：`_bump()` 是**次版本 +1**（`agent/mcp-server/server.py:341`）。`v0.9` 调一次 bump 得到 `v0.10`，不会跳到 `v1.0`。要发 `v1.0` 必须显式传 `version="v1.0"` 给 `onto_commit`。这一点 §5.1 的链路图没写清楚，容易让人以为会自动进位。

---

## 2 实体类型（6 类）

| 类型 | 含义 | ID 前缀 | 实测实例数 | 举例 |
| --- | --- | --- | --- | --- |
| `Disease` | 疾病／病种／综合征 | 直接用 ICD-10 码，或 `ICD10-<码>`（标准节点） | 7 | `K27` 消化性溃疡、`K29` 胃炎、`K21` 胃食管反流、`R10.1` 上腹部痛、`ICD10-K27` |
| `Symptom` | 症状／体征 | `SYM-` | 2 | `SYM-EPI` 上腹隐痛、`SYM-HEART` 反酸／烧心 |
| `Exam` | 检查／检验项目 | `EX-` | 2 | `EX-GASTRO` 胃镜、`EX-HP-BT` 幽门螺杆菌呼气试验 |
| `Drug` | 药品／药物类别 | `DRUG-` | 1 | `DRUG-IBU` 布洛芬 |
| `Department` | 科室 | `DEP-` | 1 | `DEP-GI` 消化内科 |
| `Finding` | 检验结果／指标值 | `FIND-` | **0** | 尚无实例（见下方说明） |

**`Finding` 目前是空类，这是有意的，不是漏写。**

`agent/` 下全仓 grep `Finding` 只命中两份文档（本文件与方案 §5.1），代码和库里一次都没有。原因是：检验结果要落到具体数值区间（"血红蛋白 < 110 g/L"），而现在的 `TableParser` 只把表格行切成分句，切不出「指标名 + 阈值 + 单位」三元结构。所以 `Finding` 定义保留、`v0.9` 不用、也不许临时拿 `Exam` 顶替——`Exam` 是"做什么检查"，`Finding` 是"检查出来的数"，两者混淆会让 `requires_exam` 的语义崩掉。

启用 `Finding` 的前置条件：T5 的表格解析能输出「指标 - 阈值 - 单位」，否则不进本体。这一条写在这里，是为了防止 W2–W3 有人为了凑实体类型数硬塞。

### 2.1 节点 ID 规则

- 一个概念**只有一个 canonical ID**。`K27` 是疾病节点，`ICD10-K27` 是它对应的标准节点，两者是**不同节点**，靠 `aligned_to_standard` 边连接。
- ID 里不放空格、中文、大小写混写。`SYM-EPI` 不是 `sym-epi`。
- 同义不新建节点：走 `alias` 表（§4.3）。「胃溃疡」「消化性溃疡」都映射到 `K27`。
- 标准节点的 ID 一律 `ICD10-<码>`。将来接临床路径标准时用 `CP-<条目号>`，不要复用 `ICD10-` 前缀。

### 2.2 实体 label

`head_label` / `tail_label` 存**中文正名**，不存编码、不存英文。`K27` 的 label 是「消化性溃疡」。理由：报告要打印给人看，label 在库里就能拿到，不用每次反查。

---

## 3 关系类型（8 类）

| # | rel | 头类型 | 尾类型 | 实测条数 | 语义一句话 |
| --- | --- | --- | --- | --- | --- |
| 1 | `has_symptom` | `Disease` | `Symptom` | 3 | 某病会有某症状 |
| 2 | `diagnosed_by` | `Symptom` | `Disease` | 1 | 某症状指向某确诊病 |
| 3 | `treated_by` | `Disease` | `Drug` | **0** | 某病用某药治 |
| 4 | `contraindicated_for` | `Drug` | `Disease` | 1 | 某药禁用于某病 |
| 5 | `requires_exam` | `Disease` | `Exam` | 5 | 某病要做某检查 |
| 6 | `belongs_to_dept` | `Disease` / `Symptom` | `Department` | 4 | 归口到某科室 |
| 7 | `subclass_of` | `Disease` | `Disease` | **0** | 上下位（子类 → 父类） |
| 8 | `aligned_to_standard` | `Disease` | 标准节点 | 3 | 本体节点 ↔ 标准编码 |

合计 17 条，与 `v0.9` 快照 `triple_count` 一致。

### 3.1 类型约束是硬规则

头尾类型写错不是"数据质量问题"，是**写坏了**，`add_triple` 之外的上游必须挡住：

- `requires_exam` 的头必须是 `Disease`、尾必须是 `Exam`。头写成 `Symptom` 会造出「上腹隐痛 → 要做 → 胃镜」，这在临床上不成立（症状不直接开检查，中间必须先落到病）。
- `contraindicated_for` 的头必须是 `Drug`。**头尾反了就是另一条知识**，代码里 `REVERSE_TOLERANT = {"contraindicated_for"}`（`agent/mcp-server/server.py:177`）专门处理「疾病患者禁用某药」与「某药禁用于某疾病」两种表述判重，但**入库方向统一为 Drug→Disease**。
- `belongs_to_dept` 允许 `Symptom` 当头（"上腹隐痛归消化内科"是分诊要用的），这是唯一的双头类型关系。
- `subclass_of` 禁止成环。`K21 subclass_of K21` 必须在写入前拒掉。

### 3.2 `treated_by` 和 `subclass_of` 现在是空的

`v0.9` 里这两类一条都没有：种子库只有一份临床路径摘要（`AST-2026-000137`），里面没有给药方案和病种层级。这不是缺陷——W2 起 T4 做 `onto_propose` 扩库时会自然长出来。但**汇报时不能说"8 类关系已全部落地"**，只能说"8 类已定义、6 类有实例"。

### 3.3 `aligned_to_standard` 与 `standard` 字段是冗余的

同一条事实存了两遍：

```json
// 写法 A：边
{"head": {"id": "K27"}, "rel": "aligned_to_standard", "tail": {"id": "ICD10-K27"}}
// 写法 B：字段
{"head": {"id": "K27"}, "rel": "requires_exam", ..., "standard": {"scheme": "ICD-10", "code": "K27"}}
```

`v0.9` 里两种都有（3 条边 + 17 条都带 `standard_json`）。**暂时都保留**，因为两种查询路径都有人用：`kg_query` 走边能多跳，`std_align` 读字段能直接拿编码。代价是差分时同一条知识会变两次。裁决留到 §9 第 6 条。

---

## 4 三元组结构

### 4.1 字段表

以 `triple` 表 17 列为准（`agent/mcp-server/store.py:35-51`）：

| 字段 | 类型 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `triple_id` | TEXT | 是 | 自动 `T-` + 8 位 hex | 主键。显式传入则用传入值 |
| `head_id` | TEXT | 是 | — | 头实体 canonical ID |
| `head_type` | TEXT | 是 | — | 6 类之一 |
| `head_label` | TEXT | 是 | — | 中文正名 |
| `rel` | TEXT | 是 | — | 8 类之一 |
| `tail_id` | TEXT | 是 | — | 尾实体 canonical ID |
| `tail_type` | TEXT | 是 | — | 6 类之一 |
| `tail_label` | TEXT | 是 | — | 中文正名 |
| `confidence` | REAL | 否 | `0.8` | 0–1。抽取产出统一 `0.72`（`server.py:241`） |
| `asset_id` | TEXT | **是** | — | 出处资产。**空 = 不许入库** |
| `anchor_id` | TEXT | **是** | — | 出处锚点，格式 `<asset_id>#<段内路径>` |
| `standard_json` | TEXT | 否 | `{}` | `{"scheme": "ICD-10", "code": "K27"}` |
| `status` | TEXT | 否 | `active` | `active` / `deprecated`。查询只看 `active` |
| `version_added` | TEXT | 否 | 当前版本 | 首次入库的快照号 |
| `version_removed` | TEXT | 否 | `NULL` | 废弃时的快照号 |

### 4.2 JSON 形态（对外）

`_triple_out()`（`agent/mcp-server/store.py:212`）输出的形状，这是 `kg_query` 的 `steps[].` 内容：

```json
{
  "triple_id": "T-26d3fa64",
  "head": {"id": "K27", "type": "Disease", "label": "消化性溃疡"},
  "rel": "requires_exam",
  "tail": {"id": "EX-HP-BT", "type": "Exam", "label": "幽门螺杆菌呼气试验"},
  "confidence": 0.92,
  "provenance": {
    "asset_id": "AST-2026-000137",
    "anchor_id": "AST-2026-000137#s3.p1.c1"
  },
  "standard": {"scheme": "ICD-10", "code": "K27"},
  "version_added": "v0.9"
}
```

**注意两处与方案 §5.1 的差异**（已核到代码行，以代码为准）：

1. §5.1 的示例里 `provenance` 含 `source_type` 字段。`_triple_out` 和 `triple` 表**都没有**这个字段——`provenance` 只有 `asset_id` + `anchor_id` 两个键。
2. §5.1 的示例里 `status` / `version_removed` 在 JSON 里。`_triple_out` **不输出**这两个键，只输出 `version_added`。

下游按本文的字段名写，不按 §5.1 的示例 JSON 写。

### 4.3 别名表 `alias`（独立于三元组）

同义词不建节点，进 `alias` 表（`store.py:72-78`）：

| 列 | 说明 |
| --- | --- |
| `surface` | 自由文本（主键） |
| `code` | canonical ID 或标准码 |
| `scheme` | `local` / `ICD-10` |
| `entity_type` | 6 类之一 |
| `confidence` | 默认 `0.9` |

`v0.9` 有 12 条。多对一是正常的：`消化性溃疡` 与 `胃溃疡` 都是 `K27`。

**已知问题**：`上腹部痛` 映射到 `R10.1` 且 `entity_type=Symptom`，但三元组里 `R10.1` 被当成 `Disease` 当头（`T-d2e6d769`）。同一个 ID 在两处类型不一致。裁决见 §9 第 5 条。

---

## 5 provenance 与 `source_type` 三值

### 5.1 provenance 是硬门槛

**没有出处的三元组不许进本体。** 这不是风格要求，是 R4 溯源分的物理基础：报告里每个结论都要能点回原文某一句。所以 `asset_id` + `anchor_id` 在 `v0` 里是**必填**，`add_triple` 之外没有旁路。

`anchor_id` 的格式：`<asset_id>#<段内路径>`

| 段内路径形态 | 含义 | 实例 |
| --- | --- | --- |
| `s<n>.h` | 第 n 个 section 的标题 | `AST-2026-000137#s2.h` |
| `s<n>.p<m>.c<k>` | 第 n 段第 m 句第 k 个分句 | `AST-2026-000137#s3.p1.c1` |
| `t<n>.r<m>` | 第 n 张表第 m 行（表格模态） | `AST-2026-59622c#t1.r2` |

实测：`AST-2026-000137` 共 15 个锚点，`sentence` 10 个、`section` 5 个。

### 5.2 `source_type` 三值（存在资产侧，不在三元组侧）

方案 §5.1 规定三值锁定「这条知识该由谁背书」。三值本身对，但要写清它落在哪：

| 取值 | 含义 | 能承担 | 不能承担 |
| --- | --- | --- | --- |
| `icd10` | 编码表映射 | 症状／诊断 → 编码归一 | 病种鉴别、检查推荐 |
| `pathway` | 临床路径／诊疗指南 | 症状 → 病种鉴别入口、病种 → 检查项 | 药品禁忌 |
| `drug_label` | 药品说明书 | 禁忌、不良反应、相互作用 | 诊断与检查 |

**实际落点**：代码里 `source_type` 只出现在 `ingest_asset` 的入参（`server.py:64`，默认 `"public_standard"`），写进 `asset.source_json.type`，三元组表里没有这一列。

所以现在**没法在单条三元组上判断 source_type**，只能顺着 `asset_id` 反查。这够用，但要写进 T4 的对齐校验：`contraindicated_for` 的边必须挂在 `drug_label` 资产上，如果挂在 `pathway` 上就是抽错了。

`v0` 的裁决：**不新增列**，用反查。理由见 §9 第 1 条。

---

## 6 其余命名规范

| 对象 | 规则 | 实例 |
| --- | --- | --- |
| 资产 ID | `AST-<年>-<6 位 hex>` | `AST-2026-000137`、`AST-2026-59622c` |
| 三元组 ID | `T-` + 8 位 hex | `T-26d3fa64` |
| 抽取批次 | `DF-` + 8 位 hex | `DF-a1b2c3d4` |
| 快照文件 | `ontology_<版本>.jsonl` | `ontology_v0.9.jsonl` |
| 快照 manifest | `sha256(triple_id\|head_id\|rel\|tail_id\|confidence)` 前 16 位 | `49c493fd8f91b0d3` |

manifest 的拼接格式是 `snapshot()` 里写死的（`store.py:350-370`），换字段就会让历史 manifest 失效，**不要动**。

---

## 7 抽取约束：阈值是 12 字，不是 30 字

方案 §5.2 的第 5 条硬规则**原写**「段落长度 < 30 字或全是表头的，不抽」，已于 2026-10-29 同步改为 12 字。代码一直是 **12**（`agent/mcp-server/server.py:221`）。

**以 12 为准**，因为拿真实数据算过：

| 阈值 | 15 个锚点里能过的 | 通过率 |
| --- | --- | --- |
| ≥ 30 字 | 1 | 6.7% |
| ≥ 12 字 | 8 | 53.3% |

按 30 字卡，这份临床路径只能抽出 1 条三元组，`onto_propose` 等于废掉。而且临床上"确诊依赖胃镜检查与病理"这种 11 字短句信息密度反而最高。

裁定：**阈值 12 字，方案 §5.2 的 30 字是笔误**，§9 登记为已裁决项。

---

## 8 五条校验规则 → 各自的落点

| # | 规则 | 落在哪 | 现在的实现状态 |
| --- | --- | --- | --- |
| 1 | 头尾必须能落到已有节点或 ICD-10 编码 | `store.resolve_entity()`（`store.py:458`） | ✅ 已实现。先查 `head_label`，再查 `alias` |
| 2 | 关系与实体类型必须匹配 | 抽取侧 | ⚠️ 部分。`onto_propose` 硬编码头 `Disease`、尾 `Exam`/`Disease`（`server.py:234`、`:238`），**不看实际类型** |
| 3 | 同 `(head, rel, tail)` 已有 active 则判重不新增 | `store.add_triple()`（`store.py:171`） | ✅ 已实现。重复时只把 `confidence` 取 `max()` 更新，返回 `None` |
| 4 | 语义冲突（如 `contraindicated_for` 与 `treated_by` 同时成立）标冲突 | 待 T4 | ❌ 未实现 |
| 5 | 段落 < 12 字或全是表头的不抽 | `server.py:220` | ✅ 已实现（阈值见 §7） |

第 2 条是 `v0` 最大的实现缺口，具体见 §9 第 2 条。

---

## 9 与实现的差异清单

按「会不会在答辩现场翻车」排序。第 1–3 条必须有人认领，第 4 条之后可以选择不修但必须能解释。

| # | 差异 | 影响 | 裁决 |
| --- | --- | --- | --- |
| 1 | `source_type` 三元组侧无列，只能靠 `asset_id` 反查 | 单条边不能自证"谁背书" | **接受**。反查成本低，加列会让 `snapshot()` 的 manifest 格式变更 |
| 2 | `onto_propose` 头类型硬编码 `Disease` | 「布洛芬禁用于消化性溃疡」抽出来头类型是 `Disease` 而不是 `Drug`，**方向会反** | **必修**，T2 在 2.2 改成按 `resolve_entity` 查到的 `entity_type` 取类型。不修则 `contraindicated_for` 全废 |
| 3 | 代码会产出 `may_cause`，但 8 类关系里没有这一类 | `PATTERNS` 第 2 条正则（`server.py:162-168`）匹配「可导致」输出 `rel="may_cause"`，写库后被 §3 的表判为非法 | **已裁决：加为第 9 类**，随 schema v1 在 W3 与 `v1.0` 快照一起落地（理由见 §9.1）。在此之前 T2 的 `agent/ontology/extract.py` 可产出 `may_cause` 候选，但入库前要标 `pending` |
| 4 | `aligned_to_standard` 边与 `standard_json` 字段冗余 | 差分同一条知识双份变化 | **暂留**。见 §3.3 |
| 5 | `R10.1` 在 `alias` 里是 `Symptom`，在三元组里当 `Disease` 用 | 同一 ID 两处类型打架 | **待裁决**。倾向把 `R10.1` 改成 `Symptom`，但 `T-d2e6d769` 的 `has_symptom`（症状→症状）仍然不合法，需 T4 重抽 |
| 6 | `_bump()` 次版本 +1，`v0.9` → `v0.10` | 想发 `v1.0` 必须显式传参，容易被忽略 | **接受**，写进 §1 当操作常识 |
| 7 | `snapshot()` 写死 `DATA_DIR`，不认 `MEDPAL_DB` | 用副本库跑测试仍会往 `agent/mcp-server/data/` 写快照，污染工作区 | **接受**（已知），跑测试后记得 `git status` 看一眼 |

### 9.1 关于第 3 条的补充

`may_cause` 不是随手写的。`v0.9` 里有一条真实证据支持它：锚点 `AST-2026-000137#s4.p1.c1` 原文是「布洛芬可导致胃黏膜损伤」——这是药品不良反应，属于 `drug_label` 该背书的知识，而 8 类关系里**没有任何一类能表达"导致"**。`contraindicated_for` 表达的是"禁用"，强度完全不同。所以这是 schema 缺一类，不是代码多写一类。**2026-10-29 裁定：加 `may_cause` 为第 9 类**，升 schema v1，时间点放在 W3 与 `v1.0` 快照一起（与 §9 第 3 条同一结论）。

---

## 10 各方按本文读什么

| 角色 | 读哪些字段 | 不许做的事 |
| --- | --- | --- |
| T2 建图 / 推理 | `head_id` `rel` `tail_id` `confidence` `provenance` | 不许在遍历时自己造节点 ID；不许改 `status` 语义 |
| T4 对齐 / 差分 | `standard_json` `status` `version_added` `version_removed` | 不许改 `triple_id`；不许绕过 `add_triple` 直接 `INSERT` |
| T5 建库 | `head_label` `tail_label` + `anchor_id` 指回原文 | 不许把 `alias.surface` 当独立实体入库 |
| T3 可视化 | `provenance.anchor_id` 拆 `#` 前段定位资产、后段定位句 | 不许假设 `anchor_id` 一定含 `#` |

---

## 11 改结构的流程

1. 在本文件 §9 提一条差异记录，写清改什么、为什么、影响谁；
2. T1 裁决。裁决结论写回 §9 的「裁决」列；
3. 改本文件的版本号 `v0` → `v1`，并在 §12 追加变更行；
4. 改代码（`store.py` 的 DDL / `server.py` 的校验）；
5. 跑 `python agent/tests/test_mcp_client.py`，必须 `MCP CLIENT OK`；
6. 通知 T2 / T4 / T5 / T3。

**只改数据不改结构不需要走这个流程**——`onto_propose` → `onto_commit` 那条路随便走。

---

## 12 变更记录

| 版本 | 日期 | 变更 |
| --- | --- | --- |
| v0 | 2026-10-29 | 首次冻结：6 类实体、8 类关系、17 个字段、12 字阈值、9 条差异登记 |

---

## 附录 A 种子 v0.9 全量 17 条

供 T2 / T4 对照，避免各自猜 ID。

| triple_id | head | rel | tail | conf |
| --- | --- | --- | --- | --- |
| `T-0f5bfa1d` | K29 胃炎 | requires_exam | EX-GASTRO 胃镜 | 0.86 |
| `T-1eaa1c36` | K29 胃炎 | belongs_to_dept | DEP-GI 消化内科 | 0.90 |
| `T-26d3fa64` | K27 消化性溃疡 | requires_exam | EX-HP-BT 幽门螺杆菌呼气试验 | 0.92 |
| `T-3604ada3` | K21 胃食管反流 | belongs_to_dept | DEP-GI 消化内科 | 0.88 |
| `T-41ce88d4` | K29 胃炎 | requires_exam | EX-HP-BT | 0.84 |
| `T-4d2cc4f0` | K27 消化性溃疡 | requires_exam | EX-GASTRO 胃镜 | 0.90 |
| `T-4f75c14d` | K29 胃炎 | aligned_to_standard | ICD10-K29 | 0.99 |
| `T-5d2c1402` | K21 胃食管反流 | aligned_to_standard | ICD10-K21 | 0.99 |
| `T-7c93f5c4` | K21 胃食管反流 | has_symptom | SYM-HEART 反酸 | 0.85 |
| `T-8cae00d8` | K21 胃食管反流 | requires_exam | EX-GASTRO 胃镜 | 0.80 |
| `T-accfbc05` | K27 消化性溃疡 | belongs_to_dept | DEP-GI 消化内科 | 0.95 |
| `T-b5d99245` | K27 消化性溃疡 | aligned_to_standard | ICD10-K27 | 0.99 |
| `T-c81c915c` | SYM-EPI 上腹隐痛 | belongs_to_dept | DEP-GI 消化内科 | 0.80 |
| `T-d2e6d769` | R10.1 上腹部痛 | has_symptom | SYM-EPI 上腹隐痛 | 0.90 |
| `T-d331cf32` | SYM-EPI 上腹隐痛 | diagnosed_by | K27 消化性溃疡 | 0.78 |
| `T-e3f00e1e` | DRUG-IBU 布洛芬 | contraindicated_for | K27 消化性溃疡 | 0.88 |
| `T-e63cac65` | K29 胃炎 | has_symptom | SYM-EPI 上腹隐痛 | 0.70 |

置信度分布：min 0.70 / max 0.99 / avg 0.878。`status` 全部 `active`，`version_removed` 全部 `NULL`，`version_added` 全部 `v0.9`。

---

## 附录 B 取证命令

本文每个数字都能自己复现：

```bash
# 表结构
grep -n "CREATE TABLE" -A 17 agent/mcp-server/store.py

# 17 条的分布（实体类型 / 关系 / 置信度）
cd agent/mcp-server && python -B -c "
import sqlite3, collections
c = sqlite3.connect('data/medpal.db')
print('relations:', collections.Counter(r[0] for r in c.execute('select rel from triple')))
print('head_type:', collections.Counter(r[0] for r in c.execute('select head_type from triple')))
"

# 锚点长度分布（验证 12 字阈值）
cd agent/mcp-server && python -B -c "
import sqlite3, json
c = sqlite3.connect('data/medpal.db')
a = json.loads(c.execute('select anchors_json from asset').fetchone()[0])
ls = [len(x['text']) for x in a]
print('>=30:', sum(1 for x in ls if x >= 30), '/', len(ls))
print('>=12:', sum(1 for x in ls if x >= 12), '/', len(ls))
"

# 版本 bump 行为
cd agent/mcp-server && python -B -c "
import re
src = open('server.py', encoding='utf-8').read()
m = re.search(r'def _bump\(v: str\) -> str:.*?\n\n\n', src, re.S)
ns = {}; exec(m.group(0), {'re': re}, ns)
print('v0.9 ->', ns['_bump']('v0.9'))
print('v1.0 ->', ns['_bump']('v1.0'))
"
```

Windows 下跑要加 `PYTHONIOENCODING=utf-8`，否则中文列名会抛 `UnicodeEncodeError`。
