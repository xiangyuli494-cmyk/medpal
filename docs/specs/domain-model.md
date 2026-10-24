# 领域模型 v0.1

> 状态：W1 冻结最小可用字段集，W2 评审确认冻结。
> 契约来源：`docs/plan/11-技术方案与接口契约.md` §4.3（实体字段）、§4.3.8（最小可用字段集与冻结口径）。
> 状态机来源：`docs/plan/02-系统设计规格说明书.md` §3.3（11 个节点）。
> 口径裁决：`W1-开工包/04-口径裁决表.md` 第 1、4、11、12 条。
> 本文件是字段口径的唯一来源。11 号 §4.3 为契约级摘要，两者冲突时以本文件为准，并回头修 11 号。

---

## 1 实体总览

9 个实体：11 号 §4.3 的 8 个，加 04 号裁决第 11 条补的 `Media`。

| # | 实体 | 中文 | 最小可用字段数 | 可延后字段数 | 冻结版本 | 来源 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | `Episode` | 陪诊单 | 7 | 2 | v0.1（W1） | 11 号 §4.3.1 |
| 2 | `Timeline` | 时间轴 | 5 | 1 | v0.1（W2） | 11 号 §4.3.2 |
| 3 | `Task` | 待办任务 | 6 | 1 | v0.1（W2） | 11 号 §4.3.3 |
| 4 | `Memory` | 长期记忆 | 3 | 2 | v0.1（W2） | 11 号 §4.3.4 |
| 5 | `Consent` | 授权 | 5 + 1 规则项 | 0 | v0.1（W2） | 11 号 §4.3.5 |
| 6 | `AuditLog` | 调用留痕 | 7 | 1 | v0.1（W2） | 11 号 §4.3.6 + 裁决 12 |
| 7 | `User` | 用户 | 3 | 1 | v0.1（W1） | 11 号 §4.3.7 |
| 8 | `AccessibilityProfile` | 无障碍档案 | 3 | 3 | v0.1（W2） | 11 号 §4.3.7 |
| 9 | `Media` | 材料 | 5 | 0 | v0.1（W2） | 04 号裁决 11 |

主干实体是 `Episode`。三端（设备端、用户端、家属端）读写的都是同一个 `Episode`，这是「一端三通道」在数据层的落点。设备端是本体，用户端与家属端是它的两个远程延伸。

---

## 2 状态机

### 2.1 状态枚举

按 04 号裁决第 1 条，状态机按 11 个节点实现，命名统一为大写下划线，与代码枚举逐字一致。

```python
class EpisodeStatus(StrEnum):
    ARRIVED = "ARRIVED"                # 抵达确认
    BRIEFING = "BRIEFING"              # 行程播报
    REGISTER = "REGISTER"              # 取号挂号
    WAITING = "WAITING"                # 候诊盯号
    IN_ROOM = "IN_ROOM"                # 进诊室
    RECAP = "RECAP"                    # 复述校验
    PLAN_EXAMS = "PLAN_EXAMS"          # 检查规划
    NAVIGATE = "NAVIGATE"              # 执行与导航
    PAY_AND_PICKUP = "PAY_AND_PICKUP"  # 缴费取药
    REPORT = "REPORT"                  # 看报告
    HOME = "HOME"                      # 小结回家
```

命名替换登记：W1 开工包里的 `陪诊状态机.puml` 曾用 `PLAN` / `NAV` / `PAY` 三个缩写作为别名，本文件起统一为 `PLAN_EXAMS` / `NAVIGATE` / `PAY_AND_PICKUP`，图文件同步改。

### 2.2 节点表

每个节点四件事必须有答案：怎么进、怎么出、能不能被打断、写什么进时间轴。缺一栏的节点不算定义完。

| # | 状态 | 进入条件 | 出口条件 | 可被打断 | 时间轴写入 |
| --- | --- | --- | --- | --- | --- |
| 1 | `ARRIVED` | 服务台登记（报姓名与年龄段）并绑定设备编号，`Episode` 创建（**无读卡器，不刷证件**，ADR-019） | 用户确认到院 → `BRIEFING` | 是 | 到院时刻、确认方式 |
| 2 | `BRIEFING` | `ARRIVED` 出口 | 当日行程播报完毕 → `REGISTER` | 是 | 播报文本、是否被打断重播 |
| 3 | `REGISTER` | `BRIEFING` 出口 | 取号成功（号票号写入 `Task`） → `WAITING` | 是 | 科室、号序、排队人数 |
| 4 | `WAITING` | `REGISTER` 出口 | 叫号（剩余 ≤ 3 位时提醒） → `IN_ROOM` | 是 | 每次叫号提醒、当前号序 |
| 5 | `IN_ROOM` | `WAITING` 出口 | 出诊室 → `RECAP` | 是 | 进诊室与出诊室时刻 |
| 6 | `RECAP` | `IN_ROOM` 出口 | 用户确认复述 → `PLAN_EXAMS`；用户否认 → 留在本节点重问 | 是 | 医嘱原文、复述文本、确认结果 |
| 7 | `PLAN_EXAMS` | `RECAP` 出口 | 检查排序确定 → `NAVIGATE` | 是 | 检查项、排序依据、预计耗时 |
| 8 | `NAVIGATE` | `PLAN_EXAMS` 出口 | 全部检查完成 → `PAY_AND_PICKUP` | 是 | 每一段导航的起点终点与步数 |
| 9 | `PAY_AND_PICKUP` | `NAVIGATE` 出口 | 缴费完成且取药完成 → `REPORT` | 是 | 费用明细、取药凭证（`Media`） |
| 10 | `REPORT` | `PAY_AND_PICKUP` 出口 | 报告已读并通俗化播报完毕 → `HOME` | 是 | 报告原文、通俗化文本、免责声明挂载点 |
| 11 | `HOME` | `REPORT` 出口 | 陪诊小结生成、`Episode` 置为已结束 | 否 | 小结、总时长、求助次数 |

硬约束两条：

1. **状态权威在服务端。** 客户端不得自行推进节点，收到 `state.transition` 才改本地状态（见 `docs/api/ws-protocol.md` §1）。
2. **不得跳步。** 只允许 `n → n+1`，唯一例外是进入 `FALLBACK` 后原路返回。

### 2.3 11 → 9 展示映射

对外（演示、答辩、家属端进度条）讲 9 步，系统内部仍按 11 个状态实现。这张表就是两套说法的转换器。

| 对外步序 | 对外名称 | 覆盖的系统状态 | 说明 |
| --- | --- | --- | --- |
| 1 | 抵达确认 | `ARRIVED` | 一对一 |
| 2 | 行程播报 | `BRIEFING` | 一对一 |
| 3 | 取号挂号 | `REGISTER` | 一对一 |
| 4 | 候诊盯号 | `WAITING` | 一对一 |
| 5 | 进诊室 | `IN_ROOM` | 一对一 |
| 6 | 复述校验 | `RECAP` | 一对一 |
| 7 | 检查规划 | `PLAN_EXAMS` | 一对一 |
| 8 | 执行与导航 | `NAVIGATE` | 一对一 |
| 9 | 缴费取药与看报告 | `PAY_AND_PICKUP` + `REPORT` | 两状态合一，报告在取药后当场读 |
| 收尾 | 小结回家 | `HOME` | 不计入 9 步，作为结束动作 |

换算规则（设备端与家属端进度条实现用）：

```
对外步序 = 9,                                    当 status in (PAY_AND_PICKUP, REPORT)
对外步序 = 1..8,                                 当 status 是前 8 个
对外步序 = None,                                 当 status == HOME（显示「已完成」）
```

同步改动：`docs/plan/02-系统设计规格说明书.md` §3.3 已补一句指向本表的说明。改完已 grep 全库，除演示脚本自身的「9 步巡演」（`demo/README.md:21`、`02 号:224`，指演示流程而非状态节点）外，无第三处仍在说「9 个节点」。

### 2.4 兜底子状态机

任意节点都能被三句话打断，进入 `FALLBACK`，处理完回到原节点，不得跳步。

| 触发语句 | 兜底分支 | 处理完回到 |
| --- | --- | --- |
| 「我不懂」 | 换一种说法重讲当前节点要点 | 原节点 |
| 「我找不到」 | 重新导航，或推送服务台工单 | 原节点（导航类节点回到 `NAVIGATE`） |
| 「我要找人」 | 转院内服务台，会话不断开 | 原节点 |

`FALLBACK` 不是第 12 个状态，它是所有节点共享的子状态机，`Episode.status` 在兜底期间保持原值不变，只额外记 `fallback_from`。

### 2.5 跨切面能力

四个能力对全部 11 个节点生效，不单独占状态。

| 能力 | 要求 | 数据落点 |
| --- | --- | --- |
| 记忆 | 进入节点时先查 `Memory`，命中则代入称呼与过敏史 | `Memory` |
| 主动 | 静默超过 12 秒触发主动关怀；到点未执行触发提醒 | `Timeline` |
| 兜底 | 见 §2.4 | `Timeline` + `Task`（升级工单） |
| 留痕 | 每次状态跃迁写一条 `Timeline` | `Timeline` |

---

## 3 实体字段

字段命名规则：中文名给人看，`snake_case` 标识符给代码用。标识符在全项目唯一，术语表 `docs/00-术语表.md` 收录同一批标识符，两处不得出现第二种拼法。

### 3.1 Episode 陪诊单

| 字段 | 标识符 | 分类 | 类型 | 说明 |
| --- | --- | --- | --- | --- |
| 陪诊单标识 | `id` | 最小可用 | str | 全局唯一 |
| 状态 | `status` | 最小可用 | `EpisodeStatus` | 见 §2.1 |
| 院内对接人 | `staff_contact` | 最小可用 | str \| None | 服务台或导医台当班人员的工号，用于升级工单派员与回执；用户自助完成全程时为空 |
| 授权记录 | `consents` | 最小可用 | list[`Consent`] | 见 §3.5 |
| 时间轴 | `timeline` | 最小可用 | list[`Timeline`] | 见 §3.2 |
| 待办任务 | `tasks` | 最小可用 | list[`Task`] | 见 §3.3 |
| 材料 | `media` | 最小可用 | list[`Media`] | 见 §3.10 |
| 事件流 | `events` | 可延后 | list[`Event`] | 与 `timeline` 重叠，W4 前只保留时间戳与类型 |
| 陪诊小结 | `summary` | 可延后 | str | W6 前只存自由文本，不定义结构 |

### 3.2 Timeline 时间轴

| 字段 | 标识符 | 分类 | 类型 | 说明 |
| --- | --- | --- | --- | --- |
| 所属陪诊单 | `episode_id` | 最小可用 | str | 外键 |
| 记录时刻 | `at` | 最小可用 | datetime | 记录产生的时间 |
| 类型 | `type` | 最小可用 | enum | `photo` / `audio` / `receipt` / `text` |
| 可见范围 | `visibility` | 最小可用 | enum | `family_visible` / `family_hidden`，由 `Consent` 决定 |
| 来源 | `source` | 最小可用 | enum | `manual`（人工录入）/ `system`（系统自动） |
| 关联节点 | `node` | 可延后 | `EpisodeStatus` | W4 前由写入时刻的 `status` 推导，不单独存储 |

撤销授权后家属端即时不可见，判定依据是 `Consent.status` 与 `Consent.revoked_at`，不是 `Timeline.visibility` 的静态值。

### 3.3 Task 待办任务

| 字段 | 标识符 | 分类 | 类型 | 说明 |
| --- | --- | --- | --- | --- |
| 任务标识 | `id` | 最小可用 | str | |
| 所属陪诊单 | `episode_id` | 最小可用 | str | 外键 |
| 标题 | `title` | 最小可用 | str | 一句话说清要做什么 |
| 类型 | `type` | 最小可用 | enum | `exam` / `payment` / `pickup` / `delivery` / `escalation`。`delivery` 对应材料「已交付」确认，不是签署 |
| 状态 | `status` | 最小可用 | `TaskStatus` | `pending` / `doing` / `done` / `escalated` |
| 责任人 | `owner` | 最小可用 | str | 院内人员工号或系统角色 |
| 证据引用 | `evidence` | 可延后 | str | 指向 `Timeline` 或 `Media`；W4 前用 `timeline` 外键替代 |

### 3.4 Memory 长期记忆

跨 `Episode` 复用，归属到人而不是单。

| 字段 | 标识符 | 分类 | 类型 | 说明 |
| --- | --- | --- | --- | --- |
| 用户 | `user_id` | 最小可用 | str | 记忆归属 |
| 过敏史 | `allergy` | 最小可用 | str | 跨单复用，进入节点时必查 |
| 称呼偏好 | `salutation` | 最小可用 | str | 对用户的称呼方式 |
| 上次结果 | `last_result` | 可延后 | str | 上一次陪诊的结论性信息 |
| 既往问题 | `problems` | 可延后 | str | 上一次陪诊中出现的问题 |

### 3.5 Consent 授权

| 字段 | 标识符 | 分类 | 类型 | 说明 |
| --- | --- | --- | --- | --- |
| 授权人 | `grantor` | 最小可用 | str | 用户本人 |
| 被授权人 | `grantee` | 最小可用 | str | 家属或其他角色 |
| 授权范围 | `scope` | 最小可用 | enum | `timeline` / `media` / `report` / `all` |
| 状态 | `status` | 最小可用 | enum | `active` / `revoked` |
| 撤销时间 | `revoked_at` | 最小可用 | datetime | 撤销即时不可见的判定依据 |
| 生效规则 | `rule` | 最小可用（规则项） | — | 撤销后该通道即时不可见。**这是规则不是存储字段**，不进表结构 |

### 3.6 AuditLog 调用留痕

每次 AI 调用一条记录。

| 字段 | 标识符 | 分类 | 类型 | 说明 |
| --- | --- | --- | --- | --- |
| 输入 | `input` | 最小可用 | text | 送入模型的原始内容 |
| 输出 | `output` | 最小可用 | text | 模型返回内容 |
| 模型 | `model` | 最小可用 | str | 供应商标识与型号 |
| 耗时 | `latency_ms` | 最小可用 | int | 单次调用耗时（毫秒） |
| 是否被人工修正 | `corrected` | 最小可用 | bool | 设备端当场追问后用户改口的结果标记 |
| 所属陪诊单 | `episode_id` | 最小可用 | str | **裁决 12 新增**，缺它审计查不到「这句是哪单的」 |
| 所属节点 | `status` | 最小可用 | `EpisodeStatus` | **裁决 12 新增**，缺它查不到「哪个节点说的」 |
| 成本 | `cost` | 可延后 | decimal | 单次调用费用 |

### 3.7 User 用户

| 字段 | 标识符 | 分类 | 类型 | 说明 |
| --- | --- | --- | --- | --- |
| 用户标识 | `id` | 最小可用 | str | |
| 角色 | `role` | 最小可用 | enum | `elder` / `family` / `staff` |
| 通道偏好 | `channel_pref` | 最小可用 | enum | `elder` / `vision` / `hearing` / `standard` |
| 方言偏好 | `dialect` | 可延后 | str | W5 真实 ASR 接入前不启用 |

### 3.8 AccessibilityProfile 无障碍档案

| 字段 | 标识符 | 分类 | 类型 | 说明 |
| --- | --- | --- | --- | --- |
| 用户 | `user_id` | 最小可用 | str | 与 `User` 一对一 |
| 视力 | `vision` | 最小可用 | str | 视力障碍程度与所需字号档位 |
| 听力 | `hearing` | 最小可用 | str | 听力障碍程度，决定是否走文字优先 |
| 认知 | `cognitive` | 可延后 | str | |
| 行动 | `mobility` | 可延后 | str | |
| 识字 | `literacy` | 可延后 | str | |

### 3.9 Media 材料

04 号裁决第 11 条新增。11 号只在 `Episode` 里写了 `media[]`，没有字段定义；`Timeline` 与 `Task.evidence` 要引用它，缺了没法留痕。

| 字段 | 标识符 | 分类 | 类型 | 说明 |
| --- | --- | --- | --- | --- |
| 材料标识 | `id` | 最小可用 | str | |
| 所属陪诊单 | `episode_id` | 最小可用 | str | 外键 |
| 类型 | `kind` | 最小可用 | enum | `photo` / `audio` / `document` |
| 置信度 | `confidence` | 最小可用 | float 0–1 | 识别结果置信度，< 0.8 触发求证 |
| 是否人工校对 | `human_checked` | 最小可用 | bool | 是否已由院内人员或用户本人核对 |

---

## 4 关系与 ER 图

```
User 1 ──< Consent >── 1 User（授权人 / 被授权人）
User 1 ──< Memory
User 1 ── 1 AccessibilityProfile
Episode 1 ──< Timeline
Episode 1 ──< Task
Episode 1 ──< Media
Episode 1 ──< AuditLog（经 episode_id）
Episode 1 ──< Consent
```

图文件：

- 源文件 `docs/specs/domain-model.puml`
- 导出 `docs/specs/er.svg`、`docs/specs/er.png`

重新生成：

```bash
cd docs/specs && java -jar ../../.tools/plantuml.jar -charset UTF-8 -tsvg domain-model.puml && java -jar ../../.tools/plantuml.jar -charset UTF-8 -tpng domain-model.puml && mv domain-model-er.svg er.svg && mv domain-model-er.png er.png
```

---

## 5 最小可用字段集与冻结口径

| 实体 | 最小可用字段集 | 可延后字段 | 冻结版本 |
| --- | --- | --- | --- |
| `Episode` | `id`、`status`、`staff_contact`、`consents`、`timeline`、`tasks`、`media` | `events`、`summary` | v0.1（W1 修订） |
| `Timeline` | `episode_id`、`at`、`type`、`visibility`、`source` | `node` | v0.1（W2） |
| `Task` | `id`、`episode_id`、`title`、`type`、`status`、`owner` | `evidence` | v0.1（W2） |
| `Memory` | `user_id`、`allergy`、`salutation` | `last_result`、`problems` | v0.1（W2） |
| `Consent` | `grantor`、`grantee`、`scope`、`status`、`revoked_at`、`rule` | 无 | v0.1（W2） |
| `AuditLog` | `input`、`output`、`model`、`latency_ms`、`corrected`、`episode_id`、`status` | `cost` | v0.1（W2） |
| `User` | `id`、`role`、`channel_pref` | `dialect` | v0.1（W1） |
| `AccessibilityProfile` | `user_id`、`vision`、`hearing` | `cognitive`、`mobility`、`literacy` | v0.1（W2） |
| `Media` | `id`、`episode_id`、`kind`、`confidence`、`human_checked` | 无 | v0.1（W2） |

冻结口径（照 11 号 §4.3.8 执行，与 04 号裁决第 4 条一致）：

1. W2 冻结评审**仅受理上表「最小可用字段集」列**。可延后字段不进冻结范围，也不得以「先留位置」为由预置空字段。
2. 可延后字段的追加时点在 W4 前，以次版本号追加，追加须同时更新本文件、OpenAPI 定义与契约测试。
3. W4 范围冻结后新增字段一律转技术债台账，不在本周期实现。
4. W1 冻结的是**最小可用字段集的形状**（字段名、类型、归属），W2 评审确认后进入实现。这条落实 04 号裁决第 4 条。

---

## 6 不变量

这些规则在代码层要能被断言，不是文档里的愿望。

| # | 不变量 | 校验点 |
| --- | --- | --- |
| I1 | `Episode.status` 只由服务端推进 | 客户端收到 `state.transition` 才改状态 |
| I2 | 状态跃迁只允许 `n → n+1`，或进出 `FALLBACK` | 状态机单元测试 |
| I3 | 每次跃迁写一条 `Timeline` | 跃迁后断言 `timeline` 长度 +1 |
| I4 | `Consent.status == revoked` 后，该通道即时不可见 | 撤销后立刻查询家属端可见性 |
| I5 | 每次 AI 调用写一条 `AuditLog`，且 `episode_id`、`status` 非空 | 适配器层打点断言 |
| I6 | `Media.confidence < 0.8` 时 `human_checked` 必须为 `false` 且进入求证 | 识单流程断言 |
| I7 | `Media.human_checked` 为 `true` 时必须有对应的 `Timeline` 留痕 | 识单流程断言 |
| I8 | `Memory` 按 `user_id` 唯一，跨 `Episode` 复用 | 建单时读取断言 |

---

## 7 与 11 号的差异登记

本文件相对 11 号 §4.3 的每一处偏离都记在这里，便于 W2 评审逐条确认。

| # | 差异 | 依据 | 影响面 |
| --- | --- | --- | --- |
| D1 | 新增 `Media` 实体（5 字段） | 04 号裁决 11 | `Episode.media`、`Timeline` |
| D2 | `AuditLog` 补 `episode_id`、`status` | 04 号裁决 12 | 审计导出 |
| D3 | 状态枚举由中文序列改为大写下划线 11 个 | 04 号裁决 1、19 号步骤 2 | 三端全部 |
| D4 | `User` 补 `id` 字段 | 11 号 §4.3.7 表格漏了主键 | `Consent`、`Memory`、`AccessibilityProfile` 外键 |
| D5 | `Consent.rule` 明确标注为规则项而非存储字段 | 11 号 §4.3.5 原文即如此写，此处显式化 | 建表时不得生成该列 |
| D6 | 字段名由中文改为中文名 + `snake_case` 标识符双列 | 18 号要求「每个术语对应唯一代码标识符」 | 全项目命名 |
| D7 | `Timeline.type` 取值由中文改为英文枚举 | 与代码一致 | 设备端渲染映射 |
