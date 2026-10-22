# AI 能力探针（tools/probe）

W1 选型用的一次性测量工具。**它不绑定任何供应商 SDK**，只做三件事：发一次请求、量出延迟、把结果记账。三家各说各话的准确率没法统一，但「跑通没有」和「延迟多少」必须用同一把尺量。

## 为什么不用现成 SDK

- 业务代码禁止 import 供应商 SDK（10 号 §180，CI 会 grep）。探针虽然不在业务路径上，但用标准库更省事，也顺手验证了「只用 HTTP 就能接」这个前提；
- 各家 SDK 的鉴权、重试、超时行为各不相同，混进来就量不准延迟了。

## 环境变量

Key 只放两处：**GitHub Secrets** 或本地 `.env.local`（已被 `.gitignore` 忽略）。**截图只截变量名，不截值。**

```powershell
$env:DASHSCOPE_API_KEY = '<你的 Key>'
```

## 三步用法（DashScope 已实测确认，2026-10-20）

```powershell
# 0) 载入 Key（.env.local 已被 .gitignore 忽略）
Get-Content .env.local | Where-Object { $_ -match '^[A-Z_]+=' } | ForEach-Object {
  $k,$v = $_ -split '=',2; Set-Item -Path "env:$k" -Value $v
}

# 1) 三项能力各一条命令；--preset 已固化实测通过的端点与请求体
python tools/probe/probe.py --preset dashscope --capability asr --provider dashscope `
    --file tools\probe\samples\tts\tts_01.wav

python tools/probe/probe.py --preset dashscope --capability tts --provider dashscope `
    --text "请到二楼检验科，出电梯往左走" --voice Cherry

python tools/probe/probe.py --preset dashscope --capability ocr --provider dashscope `
    --file tools\probe\samples\ocr\01_处方单.png

# 2) 看聚合结果（延迟区间 + 按 usage 实算的单价）
python tools/probe/summary.py

# 3) 不联网自检
python tools/probe/probe.py --preset dashscope --capability tts --provider dashscope --text 测试 --dry-run
```

三项实测结果：ASR 797ms、TTS 1052–1449ms、OCR 756ms，全部 200。详见 `docs/specs/ai-selection.md` §11。

三种能力各自的必填参数：

| 能力 | 必填 | 说明 |
| --- | --- | --- |
| `asr` | `--file` 音频路径 | 实测 24kHz 也能直接喂；采集端仍按 16kHz 切帧 |
| `tts` | `--text`、可选 `--voice` | 输出 **24000 Hz** WAV；音色主观评分要另做 5 人评分 |
| `ocr` | `--file` 图片路径 | 剂量字段单独统计，见选型文档 |

## 请求体形态按各家文档改

脚本给出的是骨架 `{"model": ..., "input": {...}}`，**具体字段以各家官方文档为准**。三种改法：

- 只加字段：用 `--payload '{"parameters":{...}}'`，会与自动字段合并；
- 字段名不同（比如要 `audio` 而不是 `input.audio_base64`）：改 `probe.py` 里的 `FILE_FIELD`；
- 鉴权不是 Bearer：改 `post_json()` 里的 `Authorization` 头。

改完记得跑一次 `--dry-run` 和 `ruff check .`。

## 要记的五个数（直接填进对比表）

| 指标 | 怎么来 |
| --- | --- |
| 样本准确率 | 20 条 ASR / 10 张 OCR 的人听人看结果，脚本不替你判断对错 |
| 单价 | 各家官方价目表（元/分钟、元/千字、元/张），填进 `docs/specs/ai-selection.md` |
| 平均延迟 | `results.jsonl` 的 `latency_ms` 取平均 |
| 并发限制 | 官方文档或控制台配额页 |
| 实名 / 备案 | 开通流程里是否要求企业主体 |

## 样本目录

`tools/probe/samples/` 放音频与单据图片。**这两类文件不进仓库**（`.gitignore` 已忽略 `*.wav/*.mp3/*.m4a/*.webm`，单据图片用 `.jpg` 也会被忽略）。命名建议：

```
samples/
├── asr/01_正常_我挂的是内科.wav
├── asr/06_方言_我想问下化验单啥时候能拿.wav
└── ocr/01_挂号单.jpg
```

## 结果文件

`results.jsonl` 每行一条，字段：`capability / provider / model / status / latency_ms / excerpt / at`。每行不含 Key、不含原始音频，可以安全给队友看。文件已加入 `.gitignore`，不会误提交。
