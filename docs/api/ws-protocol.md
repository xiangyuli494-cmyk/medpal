# 会话协议 v0.1（草稿）

> 状态：W1 冻结。冻结后只允许追加版本号，不允许修改既有字段语义。

## 传输

WebSocket，JSON 控制消息 + 二进制音频帧。

## 上行（设备 → 服务端）

| type | 字段 | 说明 |
| --- | --- | --- |
| \`key\` | \`session\`, \`key\` | key 取值：\`GREEN_DOWN\` \`GREEN_UP\` \`RED_LONG\` \`SIDE\` |
| \`audio\` | \`session\`, \`seq\`, \`payload\` | 16kHz / 16bit / 单声道，每帧 200ms，base64 |
| \`touch\` | \`session\`, \`action\` | 触屏动作，如 \`confirm_yes\` |

## 下行（服务端 → 设备）

\`\`\`jsonc
{
  "type": "turn_result",
  "session": "s_123",
  "turn": 7,
  "caption":    { "text": "2 楼检验科，出电梯往左", "emphasis": ["2 楼", "往左"] },
  "speech":     { "audio_url": "https://.../t7.mp3", "rate": 0.86, "can_interrupt": true },
  "device":     { "vibrate": "confirm_twice", "haptic_after_ms": 1200 },
  "flow":       { "step": "go_to_lab", "step_index": 3, "total": 9, "why": "抽血要空腹" },
  "escalation": { "level": "none" },
  "confidence": { "asr": 0.91, "intent": 0.88 }
}
\`\`\`

\`escalation.level\` 取值：\`none\` | \`ask_again\` | \`call_staff\` | \`call_family\` | \`sos\`

## 规则

1. 设备端只做渲染与采集，不做业务判断。
2. 出现 \`escalation.level != none\` 时，设备端必须给出明确的大字下一步，不得自行编话。
3. 音频帧序号 \`seq\` 必须连续，缺帧时服务端请求重传。
4. 断线后按 \`session\` + 最后 \`turn\` 续传。

## 错误码

| code | 含义 | 处理 |
| --- | --- | --- |
| \`E_ASR_TIMEOUT\` | 识别超时 | 播报求证话术，重试 1 次 |
| \`E_ASR_LOWCONF\` | 置信度低于阈值 | 进入求证流程，不进入意图识别 |
| \`E_LLM_REFUSED\` | 生成被红线校验拦截 | 回退模板输出 |
| \`E_NET_DOWN\` | 设备离线 | 本地缓存，恢复后重放 |
| \`E_SESSION_EXPIRED\` | 会话过期 | 重新建立会话，保留 Episode |
