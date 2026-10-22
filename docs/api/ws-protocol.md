# 会话协议 v0.1

> 状态：W1 冻结（v0.1）。冻结后只允许追加次版本号与字段，不得修改既有字段语义、不得删除既有字段。
> 契约来源：`docs/plan/11-技术方案与接口契约.md` §4.4。
> 状态枚举来源：`docs/specs/domain-model.md` §2.1（11 个节点，大写下划线）。
> 错误码来源：11 号 §4.4.5（协议层 7 个）+ `docs/plan/19-W1逐人操作手册.md` 步骤 3（设备与业务层 7 个），合并为 §6 一张表。
> 本文件是 wire 格式的唯一来源。设备端、用户端、家属端与服务端 mock 一律按本文件实现。

---

## 1 传输与编码

| 项 | 约定 | 备注 |
| --- | --- | --- |
| 传输 | WSS（开发期 ws），端点 `/ws/session/{episode_id}` | 生产端口 8000，W1 mock 用 8090 |
| 控制消息 | JSON 文本帧，UTF-8，`ensure_ascii=false` | 中文直接出，不做转义 |
| 音频 | 二进制帧 | 与 JSON 帧混在同一条连接上，靠帧类型区分 |
| 音频参数 | 16000 Hz / 16 bit / 单声道，每帧 200ms | 一帧 = 3200 采样 = 6400 字节 |
| 协议版本 | `protocol_version` 字段，当前 `"0.1"` | 见 §9 |
| 保活 | 客户端发 `ping`，服务端回 `pong` | 见 §8 |
| 状态权威 | 状态机由服务端维护 | **客户端不得自行推进状态节点**，收到 `state.transition` 才改本地状态 |
| 会话标识 | `episode_id` 在 URL 上，`session_id` 由服务端在 `session.ready` 下发 | 两者不同：`episode_id` 跨重连不变，`session_id` 每次连接重发 |

`episode_id` 与 `session_id` 的区别是常见误解点：断线重连换的是 `session_id`，`episode_id` 与 `Episode` 实体一一对应，重连后仍是同一单。

---

## 2 会话生命周期

| 阶段 | 触发 | 服务端做什么 | 客户端做什么 |
| --- | --- | --- | --- |
| 建立 | 客户端发 `session.hello` | 校验 `episode_id` 与 `device_id`，回 `session.ready` 并下发当前 `state` | 收到 `ready` 后按 `state` 渲染，不假设从第一步开始 |
| 交互 | `audio.start` / `audio.chunk` / `audio.end` / `text.input` | 依次执行 ASR → 状态机 → 三层话术管线 → TTS | 播放 `tts.audio`，同时渲染 `caption.update` |
| 打断 | 客户端发 `control.barge_in` | 停止当前播报，进入新一轮识别 | 立刻静音，不等服务端确认 |
| 结束 | 客户端关闭连接，或服务端判定超时 | 会话留痕写 `Timeline`，AI 调用写 `AuditLog` | — |
| 恢复 | 断线后客户端重发 `session.hello` | 依据 `episode_id` 返回最新 `state` 与未完成 `Task` | 见 §7 |

打断是唯一「客户端先动、服务端后确认」的动作。老人按下打断时，等一个 RTT 再静音就已经晚了。

---

## 3 上行消息（设备 → 服务端）

九种，与 11 号 §4.4.3 一一对应。

| type | 发送时机 | 字段 | 说明 |
| --- | --- | --- | --- |
| `session.hello` | 连接建立后 | `protocol_version`、`device_id`、`episode_id`、`client`、`accessibility_mode` | 会话初始化。`client` ∈ `device` / `user` / `family`；`accessibility_mode` ∈ `elder` / `vision` / `hearing` / `standard` |
| `audio.start` | 开始录音 | `seq`、`sample_rate`、`encoding` | 声明音频分片序列起点。`encoding` 固定 `pcm_s16le` |
| `audio.chunk` | 录音过程中 | 二进制帧（帧头见 §3.1） | 服务端按 `seq` 重组 |
| `audio.end` | 结束录音 | `seq` | 触发 ASR 最终识别 |
| `text.input` | 文字输入 | `text` | 听障模式与兜底输入 |
| `control.barge_in` | 用户打断 | 无 | 停止当前播报 |
| `touch.event` | 触摸动作 | `target`、`action` | `target` 取设备端触摸控件标识符（见 §3.2）；`action` ∈ `tap` / `long_press` |
| `task.confirm` | 用户确认 | `task_id`、`answer` | 二元确认，用于低置信度信息。`answer` ∈ `yes` / `no` |
| `ping` | 保活 | 无 | 服务端以 `pong` 响应 |

### 3.1 二进制音频帧头

```
offset 0..3   seq        uint32 BE
offset 4..7   payload_len uint32 BE
offset 8..    payload    pcm_s16le
```

固定 8 字节头。`seq` 从 0 开始，同一 `session_id` 内单调递增，不因重连归零（归零会与服务端去重冲突）。

### 3.2 触摸控件到协议消息的映射

设备端是手持借出式陪诊机，7 寸 1024×600 横屏（`docs/specs/device-ia.md` §2、ADR-018）。屏内控件与机身五个实体键的标识符与 `touch.event.target` 的取值逐一对应，两侧不再各写一套。

**机身实体键（不看屏也能用）**

| 控件 | `target` | 上行 | 说明 |
| --- | --- | --- | --- |
| 电源 | — | 不上行 | 借还时开关机，不产生任何消息 |
| 音量－ / 音量＋ | — | 不上行 | 只改扬声器音量，属渲染参数 |
| 按住说话 | `mic` | `audio.start` / `audio.end` | 按下发 `audio.start`，松开发 `audio.end`，**不产生 `touch.event`** |
| 一键求助 | `sos` | `touch.event { target: "sos", action: "long_press" }` | 长按 1.5 秒触发；单击两次（3 秒内）等价，发 `action: "tap"` |

**顶栏与屏内控件**

| 控件 | `target` | 上行 | 说明 |
| --- | --- | --- | --- |
| 返回 | `back` | 不上行 | 纯本地退一屏，不退节点 |
| 主菜单 | `menu` | 不上行 | 纯本地换屏 |
| 主操作按钮 | `primary` | `touch.event { target: "primary", action: "tap" }` | 具体语义由当前节点决定，服务端按 `EpisodeStatus` 解释 |
| 选项胶囊 | `option:<slot_id>` | `touch.event { target: "option:<slot_id>", action: "tap" }` | `slot_id` 由服务端在 `dialog.reply.slots` 下发，设备端只回传 |
| 设置面板 | — | 不上行 | 音量、语速、方言、高对比、助听器、陪伴开关全部本地生效 |

**只有 4 类操作产生上行消息**：`mic` 走音频帧，`primary` 与 `option:*` 走 `touch.event`，`sos` 走 `touch.event` 的 `long_press`。`back` / `menu`、设置面板与电源、音量四键是纯本地交互，**不得**上行 —— 换屏与调音量都不改 `EpisodeStatus`，上行只会让服务端多一批无意义帧。

`primary` 的语义为什么不由设备端自己定：同一个按钮在 `BRIEFING` 是「我听明白了」，在 `REGISTER` 是「确认挂号」，在 `RECAP` 是「对，记住了」。设备端若自己映射，等于把状态机搬进了客户端，违反 §10 第 1 条。按钮的**文案由服务端下发**（`dialog.reply.primary_label`），设备端只负责画与回传 `target`。

这条设计与「设备端只做渲染与采集，不做业务判断」不冲突：本地控件改的是**渲染参数**（音量、语速、当前屏、陪伴开关），不改业务状态。

---

## 4 下行消息（服务端 → 设备）

十二种，与 11 号 §4.4.4 一一对应。

| type | 发送时机 | 字段 | 说明 |
| --- | --- | --- | --- |
| `session.ready` | 会话建立后 | `session_id`、`episode_id`、`protocol_version`、`state` | 返回当前状态节点 |
| `asr.partial` | 识别过程中 | `text`、`confidence` | 用于即时字幕，可高频覆盖 |
| `asr.final` | 识别完成 | `text`、`confidence` | 置信度 < 0.6 进入求证流程 |
| `state.transition` | 状态节点跃迁 | `from`、`to`、`at` | 由服务端状态机产生，客户端据此改状态 |
| `dialog.reply` | 话术生成完成 | `text`、`template_id`、`slots`、`audio_available`、`primary_label` | 由三层话术管线产出。`primary_label` 是屏内主操作按钮的文案（可空，空则不显示主操作按钮），语义由服务端按当前节点决定，见 §3.2 |
| `tts.audio` | 语音合成完成 | 二进制帧 | 承载 TTS 音频数据 |
| `caption.update` | 字幕更新 | `text` | 语音降级链的末端形态 |
| `guard.blocked` | 红线校验命中 | `rule_id`、`action` | `action` ∈ `replaced` / `escalated` |
| `task.updated` | 任务状态变更 | `task_id`、`state` | 由状态机触发 |
| `escalation.notice` | 升级人工 | `reason`、`target` | `target` ∈ `staff` / `family` / `both`。`staff` 指院内服务台，工单侧接收，不使用本项目界面 |
| `error` | 发生错误 | `code`、`message`、`retryable` | 见 §6 |
| `pong` | 保活响应 | 无 | 响应 `ping` |

### 4.1 `turn_result` 复合消息

设备端渲染一轮完整交互只需要这一条。它是 `caption.update` + `dialog.reply` + `escalation.notice` 的打包形态，W1 mock 与演示端用这个形状，W3 拆成独立消息后仍保留兼容。

```jsonc
{
  "type": "turn_result",
  "session": "s_123",
  "turn": 7,
  "caption":    { "text": "2 楼检验科，出电梯往左", "emphasis": ["2 楼", "往左"] },
  "speech":     { "audio_url": "https://.../t7.mp3", "rate": 0.86, "can_interrupt": true },
  "device":     { "vibrate": "confirm_twice", "haptic_after_ms": 1200 },
  "flow":       { "step": "NAVIGATE", "step_index": 8, "total": 11, "why": "抽血要空腹" },
  "escalation": { "level": "none" },
  "confidence": { "asr": 0.91, "intent": 0.88 }
}
```

六个字段的取值约束：

| 字段 | 子字段 | 取值 / 约束 |
| --- | --- | --- |
| `caption` | `text`、`emphasis[]` | `emphasis` 是 `text` 的子串，设备端加粗不改变文本 |
| `speech` | `audio_url`、`rate`、`can_interrupt` | `rate` 固定 0.86（老年人通道语速）；`audio_url` 为空串表示走降级链 |
| `device` | `vibrate`、`haptic_after_ms` | `vibrate` ∈ `confirm_twice`（确认短震两次）/ `error_once`（出错长震一次）/ `notice_thrice`（提示连震三次）/ `none` |
| `flow` | `step`、`step_index`、`total`、`why` | `step` 取 `EpisodeStatus` 枚举值；`step_index` 为 1–11；**`total` 固定 11**；`why` 是一句人话理由 |
| `escalation` | `level` | ∈ `none` / `ask_again` / `call_staff` / `call_family` / `sos`，判据见 §5 |
| `confidence` | `asr`、`intent` | 0–1 浮点。`asr` < 0.6 触发求证，`intent` < 0.6 触发复问 |

**`flow.total` 为什么是 11 而不是 9**：`flow` 描述的是系统状态机，状态机有 11 个节点（`docs/specs/domain-model.md` §2.1）。对外演示讲 9 步是展示层换算，由设备端按 `docs/specs/domain-model.md` §2.3 的映射表完成，不上 wire。设备端换算规则：

```
对外步序 = 9                     当 step ∈ {PAY_AND_PICKUP, REPORT}
对外步序 = step_index            当 step 是前 8 个节点
对外步序 = "已完成"              当 step == HOME
对外总步数 = 9
```

---

## 5 escalation 五级判据

五级不是形容词，是数字。阈值待 W2 联调校准，改动须改本节并升次版本号。

| level | 触发条件（全部为可测判据） | 设备端行为 | 通知谁 |
| --- | --- | --- | --- |
| `none` | 上述条件均未命中 | 正常播报 | — |
| `ask_again` | `confidence.asr < 0.6`，且本问题尚未复问过 | 复述听到的原文，问「是这个意思吗」，不推进状态 | — |
| `call_staff` | ① 同一问题连续 2 次未被理解；或 ② 用户说出「我不懂」「我找不到」「我要找人」任一（关键词命中即触发，不看置信度）；或 ③ `confidence.intent < 0.6` 连续 2 次 | 大字提示「已帮您叫服务台」，播报一句等待话术 | 院内服务台 |
| `call_family` | 老人 90 秒无任何上行输入（`ping` 不算输入） | 先本地提醒一次，30 秒后仍无输入则推送 | 家属端 |
| `sos` | 跌倒、出血、疼痛自评 ≥ 7 任一命中 | 长震一次 + 大字全屏提示 + 持续播报 | 院内服务台与家属同时（`target: "both"`） |

三句话讲清降级链（验收要求）：

1. **什么情况重问**：听不清（`asr < 0.6`），复述一遍再问一次。
2. **什么情况找服务台**：问两次还不懂，或用户自己说要找人，立刻转人工，不再自问。
3. **什么情况叫家属**：90 秒没有任何动静，或出现跌倒、出血、疼痛 ≥ 7，直接通知家属，同时通知服务台。

升级只升不降。一次会话内 `escalation.level` 不得回落到更低级别，`sos` 之后不再出现 `ask_again`。

### 5.1 语音降级链

```
云 TTS  →  浏览器 TTS  →  仅字幕
```

| 级 | 触发降级 | 降级后表现 |
| --- | --- | --- |
| 云 TTS | 正常路径 | `tts.audio` 二进制帧 |
| 浏览器 TTS | 云 TTS 失败或 `E_TTS_UNAVAILABLE` | 客户端本地合成，`caption` 照常更新 |
| 仅字幕 | 浏览器 TTS 也不可用 | 只渲染 `caption.update`，`speech.audio_url` 为空串 |

硬约束：**任一级失败都不得弹出错误框。** 用户看到的最差情况是「没有声音但有字」，不是「出错了」。验证节点 W5。

---

## 6 错误码

十四个码，分两组。两组都必须实现，协议层管连接与管线，设备业务层管老人能感知到的具体状况。

统一约定：wire 上的 `code` 一律带 `E_` 前缀。11 号 §4.4.5 表里的 `ASR_TIMEOUT` 等为文档简写，落到协议与代码时写 `E_ASR_TIMEOUT`。前缀统一属格式规范，不改变语义。

### 6.1 协议层（11 号 §4.4.5）

| code | 谁触发 | 设备端行为 | 是否重试 |
| --- | --- | --- | --- |
| `E_ASR_TIMEOUT` | 服务端：ASR 上游 8 秒无响应 | 播一句求证话术「刚才没听清，您再说一遍」，保留已录分片不清空 | 是，最多 1 次 |
| `E_ASR_EMPTY` | 服务端：识别结果为空串或全静音 | 进入求证流程，问「您刚才说话了吗」，**不中断会话、不推进状态** | 是 |
| `E_TTS_UNAVAILABLE` | 服务端或适配器：语音合成不可用 | 按 §5.1 降级链往下走一级，界面无任何错误提示 | 是 |
| `E_GUARD_BLOCKED` | 服务端：话术命中红线规则 | 按 `action` 处理：`replaced` 直接显示替换后的合规表述；`escalated` 转 `call_staff` | 否 |
| `E_STATE_CONFLICT` | 服务端：客户端上报状态与服务端不一致 | 以服务端 `state` 为准，静默刷新界面，不提示用户 | 是 |
| `E_AUTH_EXPIRED` | 服务端：令牌失效 | 静默重新获取免登录 token 后重连，用户无感 | 是 |
| `E_RATE_LIMITED` | 服务端：请求超频 | 指数退避（1s / 2s / 4s）后重试，退避期间显示「稍等一下」 | 是 |

### 6.2 设备与业务层（19 号步骤 3）

| code | 谁触发 | 设备端行为 | 是否重试 |
| --- | --- | --- | --- |
| `E_AUDIO_TOO_SHORT` | 设备端本地：按住说话时长 < 0.5 秒 | 大字提示「再按住说一次」，**不播报、不上行** | 是 |
| `E_ASR_LOW_CONF` | 服务端：`confidence.asr < 0.6` | 复述听到的原文并问「是这个意思吗」，`escalation` 置 `ask_again` | 是，最多 2 次 |
| `E_SESSION_EXPIRED` | 服务端：30 分钟无状态跃迁 | 提示「我们重新开始」，保留 `Episode` 与时间轴，不重新建单 | 否 |
| `E_TURN_OUT_OF_ORDER` | 服务端：`seq` 跳号 | 静默发 `resend(from_seq)` 请求重传，**不打扰用户** | 是 |
| `E_UPSTREAM_TIMEOUT` | 适配器：上游供应商超时 | 先播兜底话术（固定模板，不生成），再转 `call_staff` | 是，1 次 |
| `E_QUOTA_LIMIT` | 适配器：供应商限流或额度耗尽 | 转人工，不重复调用上游，避免把额度烧完 | 否 |
| `E_CONSENT_REVOKED` | 服务端：家属端撤回授权 | 家属通道无任何提示（静默失效） | 否 |

### 6.3 两组之间的关系

不是两套并列体系，是两层：协议层描述「管线哪里断了」，业务层描述「老人遇到了什么」。

| 场景 | 协议层码 | 业务层码 |
| --- | --- | --- |
| 上游 ASR 超时 | `E_ASR_TIMEOUT` | 同时上报 `E_UPSTREAM_TIMEOUT`（适配器视角） |
| 识别出来但不确定 | `E_ASR_EMPTY`（空）或直接给低 `confidence` | `E_ASR_LOW_CONF` |
| 供应商限流 | `E_RATE_LIMITED` | `E_QUOTA_LIMIT` |
| 30 分钟无跃迁 | `E_AUTH_EXPIRED`（若 token 同时过期） | `E_SESSION_EXPIRED` |

一个动作可能同时产生两层码，客户端按业务层码决定界面，按协议层码决定重连与重试策略。

---

## 7 断线续传

三个问题必须有确定答案，这是 W1 验收项。

### 7.1 重连后从哪个 turn 接着播

**从最后一个已确认送达的 `turn` + 1 开始。** 「已确认送达」的判定：客户端对收到的 `turn_result` 回一条 `ack { turn }`，服务端收到 `ack` 才认为该 turn 已送达。没收到 `ack` 的 turn 会在重连后重发。

### 7.2 `seq` 跳号怎么补

1. 设备端保留**最近 30 秒**音频帧（约 150 帧，6400 B × 150 ≈ 960 KB）。
2. 服务端发现 `seq` 跳号，发 `error { code: "E_TURN_OUT_OF_ORDER", message: "missing seq 42..45" }` 或直接发 `resend { from_seq: 42, to_seq: 45 }`。
3. 设备端从缓存里重发这些帧。
4. 缓存里没有（超过 30 秒），设备端回 `resend.failed { from_seq }`，服务端降级为「这一轮当没听到」，走 `E_ASR_EMPTY` 流程。

### 7.3 服务端消息保留多久

**30 分钟。** 超过 30 分钟按 `E_SESSION_EXPIRED` 处理：保留 `Episode` 与时间轴，会话重建，不重新建单。

### 7.4 重连时序

```
设备                     服务端
 │  (断线)
 │ ── session.hello ─────▶   带 episode_id、上次 session_id、last_turn
 │ ◀── session.ready ────    新的 session_id + 当前 state + 未完成 task[]
 │ ◀── turn_result(重发) ─    补发未 ack 的 turn
 │ ── ack { turn } ─────▶
 │ ── ping ─────────────▶
```

---

## 8 心跳

| 项 | 值 | 说明 |
| --- | --- | --- |
| 间隔 | 15 秒 | 客户端定时发 `ping` |
| 超时判定 | 连续 3 次未收到 `pong`（45 秒） | 判定连接失效，触发重连 |
| 单次等待 | 5 秒 | 5 秒内无 `pong` 记一次失败 |
| 重连退避 | 1s / 2s / 4s / 8s，上限 30 秒 | 指数退避，不无限快速重试 |
| 超时后设备端大字 | **「网络不太好，正在重新连接」** | 固定文案，不生成，不出现技术词 |
| 重连期间 | 本地继续显示最后一条 `caption` | 不清屏，避免老人以为进度丢了 |

`ping` 不算「用户输入」，不重置 90 秒无输入计时（见 §5 的 `call_family` 判据）。

---

## 9 兼容规则

照 11 号 §4.4.6 执行。

1. `protocol_version` 采用主次版本号。次版本号递增表示**向后兼容的字段追加**（新字段、新枚举值、新消息类型）。
2. **不得修改既有字段语义，不得删除既有字段。** 想改语义就升主版本号。
3. 破坏性变更须新增端点或递增主版本号，并同步更新本文件与 mock 服务。
4. 协议变更按 11 号 §4.6 执行。W2 冻结后，破坏性变更一律不在本周期受理。

本周期已登记的次版本追加：

| 追加项 | 相对 | 理由 |
| --- | --- | --- |
| `ack` 消息 | 11 号 §4.4.3 未列 | §7.1 送达确认需要 |
| `resend` / `resend.failed` | 11 号 §4.4.3 未列 | §7.2 补帧需要 |
| `error.code` 增 `E_` 前缀 | 11 号 §4.4.5 | 统一 wire 格式 |
| `touch.event` 的 `target` 取值集合 | 11 号 §4.4.3 未列 | 设备端为 7 寸触摸屏 + 机身五键（ADR-018），控件标识符需在 wire 上可判别 |
| `dialog.reply.primary_label` | 11 号 §4.4.4 未列 | 屏内主操作的文案由服务端按状态节点下发，设备端不自行映射 |

---

## 10 客户端硬规则

1. **设备端只做渲染与采集，不做业务判断。** 状态、升级、话术全部由服务端决定。
2. `escalation.level != "none"` 时，设备端**必须给出明确的大字下一步**，不得自行编话，不得只震动不显示。
3. 音频帧 `seq` 必须连续。跳号由服务端请求重传，客户端不得自行跳过。
4. 断线后按 `episode_id` + 最后已 ack 的 `turn` 续传。
5. 任何 `error` 都不得渲染成技术文案。用户能看到的只有 §8 那句「网络不太好」和 §5 的大字提示。
6. 不得弹出模态错误框。降级链的每一级都在页面内完成。

---

## 11 mock 服务

W1 的可收发验证载体，`tools/mock_ws.py`。W3 由 Django Channels 接 8000 后删除。

| 项 | 值 |
| --- | --- |
| 依赖 | `websockets`（已在 `requirements-dev.txt`，不进生产依赖） |
| 端口 | 8090（可用 `--port` 覆盖） |
| 行为 | 收到 `touch.event` 或 `text.input` 消息，回一条固定 `turn_result` |
| 固定值 | `flow.total = 11`、`flow.step = "NAVIGATE"`、`flow.step_index = 8`、`escalation.level = "none"` |

启动与自检：

```bash
# 终端 1
python tools/mock_ws.py
# mock ws: ws://127.0.0.1:8090

# 终端 2
websocat ws://127.0.0.1:8090 -t
{"type":"touch.event","session":"s_001","target":"primary","action":"tap"}
```

期望收到一条 `turn_result`，其中 `caption.text` 为中文且不乱码，`flow.total` 为 11。

注意：草稿版本里 `ws-protocol.md` 的示例曾写 `total: 9`，与 mock 的 11 冲突。按 04 号裁决第 1 条，wire 上一律为 11，对外 9 步由设备端换算（见 §4.1）。示例已改。

---

## 12 验收清单

W1 交付验收，三条全过才算冻结。

| # | 验收项 | 怎么验 | 现状 |
| --- | --- | --- | --- |
| 1 | mock 能打通 | 起 `python tools/mock_ws.py`，websocat 发一条 `touch.event`，收到 `turn_result` | 待跑 |
| 2 | 每个错误码都有「设备端行为」且是句子 | 本节 §6 逐行读，14 个码全部有整句描述 | 通过 |
| 3 | 降级链能用三句话讲清 | §5 末尾三句话 | 通过 |
| 4 | 断线续传三问有答案 | §7.1 / §7.2 / §7.3 | 通过 |
| 5 | 心跳四要素齐全 | §8：间隔、超时判定、超时后大字、重连退避 | 通过 |
| 6 | `flow.total` 全库一致为 11 | `grep -rn "total" docs/ tools/` | 通过 |
| 7 | 协议文档含核心字段 | `pytest backend/tests/test_smoke.py::test_protocol_doc_has_core_fields` | 通过 |
