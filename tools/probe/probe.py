"""AI 能力探针：用同一把尺量「跑通没有、延迟多少」，供选型对比表取数。

设计取舍
- 不 import 任何供应商 SDK（包括 dashscope），只用标准库 urllib：既不锁死供应商，
  也延续 10 号 §180「业务代码不得出现供应商 SDK import」的口径；
- URL、模型名、请求体由命令行传入：各家接口差异写在他们自己的文档里，不硬编码进仓库，
  避免「文档抄错一次，三个人按错的写」；
- 超时与重试策略与 backend/adapters/legacy/client.py 一致：只对网络错误重试一次，
  上游返回 4xx/5xx 不重试（那是 Key 或模型名不对，重发没有意义）。

用法（PowerShell，Key 只放环境变量或 GitHub Secrets）：
    $env:DASHSCOPE_API_KEY = '<你的 Key>'

    # 1) 先看请求长什么样，不联网、不需要 Key
    python tools/probe/probe.py --capability asr --provider dashscope `
        --url https://example.invalid/asr --key-env DASHSCOPE_API_KEY `
        --file tools/probe/samples/asr_01.wav --dry-run

    # 2) 真跑一次，结果追加到 tools/probe/results.jsonl
    python tools/probe/probe.py --capability asr --provider dashscope `
        --url https://<官方文档给的地址> --key-env DASHSCOPE_API_KEY `
        --file tools/probe/samples/asr_01.wav

退出码：0 上游返回 2xx；1 上游返回非 2xx；2 参数或环境问题。
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_TIMEOUT = 15.0
DEFAULT_OUT = "tools/probe/results.jsonl"
CAPABILITIES = ("asr", "tts", "ocr")
FILE_FIELD = {"asr": "audio_base64", "ocr": "image_base64"}
EXCERPT_CHARS = 300
BODY_CHARS = 4000

# 已实测确认的供应商预设（2026-10-20 实调通过，见 docs/specs/ai-selection.md §11）。
# 三者共用同一端点：现网 qwen3-asr-flash / qwen3-tts-flash / qwen3.5-ocr 都走多模态生成接口。
PRESETS = {
    "dashscope": {
        "url": "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation",
        "models": {"asr": "qwen3-asr-flash", "tts": "qwen3-tts-flash", "ocr": "qwen3.5-ocr"},
        "default_voice": "Cherry",
    },
}
MIME_BY_SUFFIX = {
    ".wav": "audio/wav",
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}
DEFAULT_OCR_PROMPT = (
    "提取单据中的药品名称、剂量、频次，以 JSON 返回；看不清的字段用 ? 表示，不要猜测"
)


def fail(message: str) -> int:
    print(f"探针失败：{message}", file=sys.stderr)
    return 2


def data_uri(path: Path, capability: str) -> str:
    """把样本文件变成 data URI；供应商实测只接受这种内联形态（传裸 base64 会 400）。"""
    mime = MIME_BY_SUFFIX.get(path.suffix.lower())
    if mime is None:
        expected = "wav/mp3/m4a" if capability == "asr" else "png/jpg/jpeg"
        raise ValueError(f"不认识的扩展名 {path.suffix!r}；{capability} 支持 {expected}")
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def read_prompt(args: argparse.Namespace) -> str:
    """OCR 提示词优先取 --prompt-file：长提示词含换行与花括号，放进命令行会被 shell 破坏。"""
    if args.prompt_file:
        path = Path(args.prompt_file)
        if not path.is_file():
            raise FileNotFoundError(f"找不到提示词文件 {path}")
        return path.read_text(encoding="utf-8").strip()
    return args.text or DEFAULT_OCR_PROMPT


def build_preset_payload(args: argparse.Namespace, preset: dict) -> dict:
    """按预设拼请求体。形态来自实测，不是照文档猜的。"""
    model = args.model or preset["models"][args.capability]
    if args.capability == "tts":
        return {
            "model": model,
            "input": {
                "text": args.text or "",
                "voice": args.voice or preset["default_voice"],
                "language_type": "Chinese",
            },
        }
    if not args.file:
        raise ValueError(f"{args.capability} 需要 --file")
    path = Path(args.file)
    if not path.is_file():
        raise FileNotFoundError(f"找不到样本文件 {path}")
    kind = "audio" if args.capability == "asr" else "image"
    content: list[dict] = [{kind: data_uri(path, args.capability)}]
    if args.capability == "ocr":
        content.append({"text": read_prompt(args)})
    return {"model": model, "input": {"messages": [{"role": "user", "content": content}]}}



def build_payload(args: argparse.Namespace) -> dict:
    """按能力拼请求体；body 形态以各家官方文档为准，这里只给一个可改的骨架。"""
    payload: dict = json.loads(args.payload) if args.payload else {}
    if args.model:
        payload.setdefault("model", args.model)
    if args.capability == "tts":
        payload.setdefault("input", {})["text"] = args.text or ""
        if args.voice:
            payload["input"]["voice"] = args.voice
        return payload
    if not args.file:
        return payload
    path = Path(args.file)
    if not path.is_file():
        raise FileNotFoundError(f"找不到样本文件 {path}")
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    payload.setdefault("input", {})[FILE_FIELD[args.capability]] = encoded
    return payload


def summarize(payload: dict) -> str:
    """打印用：把 base64 这类超长字段压成占位，避免刷屏。"""

    def shrink(value: object) -> object:
        if isinstance(value, dict):
            return {k: shrink(v) for k, v in value.items()}
        if isinstance(value, list):
            return [shrink(item) for item in value]
        if isinstance(value, str) and len(value) > 80:
            return f"<{len(value)} 字符已省略>"
        return value

    return json.dumps(shrink(payload), ensure_ascii=False, sort_keys=True)


def post_json(url: str, payload: dict, api_key: str, timeout: float) -> tuple[int, float, str]:
    """POST 一次；只对网络错误重试一次。返回 (状态码, 毫秒, 响应正文)。"""
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    last_error = ""
    for attempt in range(2):
        started = time.perf_counter()
        try:
            request = urllib.request.Request(url, data=body, headers=headers, method="POST")
            with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
                text = response.read().decode("utf-8", errors="replace")
                return response.status, (time.perf_counter() - started) * 1000, text
        except urllib.error.HTTPError as exc:
            text = exc.read().decode("utf-8", errors="replace")
            return exc.code, (time.perf_counter() - started) * 1000, text
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = str(exc)
            if attempt == 0:
                continue
    raise ConnectionError(last_error)


def record(out: str, row: dict) -> None:
    target = Path(out)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="AI 能力探针：统一测量状态码与延迟")
    parser.add_argument("--capability", required=True, choices=CAPABILITIES)
    parser.add_argument("--provider", required=True, help="供应商标签，如 dashscope / xfyun")
    parser.add_argument(
        "--preset",
        default="",
        choices=sorted(PRESETS),
        help="用已实测确认的请求形态；给了 preset 就可以省略 --url 与 --model",
    )
    parser.add_argument("--url", default="", help="完整请求地址；无 preset 时必填")
    parser.add_argument("--key-env", default="DASHSCOPE_API_KEY", help="存放 Key 的环境变量名")
    parser.add_argument("--model", default="", help="模型名，例如 qwen3-asr-flash")
    parser.add_argument("--voice", default="", help="TTS 音色（仅 --capability tts）")
    parser.add_argument("--text", default="", help="TTS 待合成文本；OCR 时作为抽取提示词")
    parser.add_argument(
        "--prompt-file",
        default="",
        help="从文件读 OCR 提示词（优先于 --text），见 docs/prompts/",
    )
    parser.add_argument("--file", default="", help="ASR 音频或 OCR 图片路径")
    parser.add_argument("--payload", default="", help="额外请求体 JSON，会与自动字段合并")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--dry-run", action="store_true", help="不联网，只打印将要发送的请求")
    args = parser.parse_args(argv[1:])

    if args.preset:
        preset = PRESETS[args.preset]
        args.url = args.url or preset["url"]
    if not args.url:
        return fail("缺少 --url；或改用 --preset dashscope")

    try:
        payload = (
            build_preset_payload(args, PRESETS[args.preset]) if args.preset else build_payload(args)
        )
    except (FileNotFoundError, ValueError) as exc:
        return fail(str(exc))

    api_key = os.environ.get(args.key_env, "").strip()
    if args.dry_run:
        print(f"[dry-run] POST {args.url}")
        print(f"[dry-run] 鉴权头：Bearer <来自环境变量 {args.key_env}>")
        print(f"[dry-run] 请求体：{summarize(payload)}")
        return 0
    if not api_key:
        return fail(f"环境变量 {args.key_env} 为空；Key 只放环境变量或 GitHub Secrets")

    try:
        status, latency_ms, text = post_json(args.url, payload, api_key, args.timeout)
    except ConnectionError as exc:
        return fail(f"网络错误（已重试一次）：{exc}")

    row = {
        "capability": args.capability,
        "provider": args.provider,
        "model": args.model,
        "status": status,
        "latency_ms": round(latency_ms, 1),
        # excerpt 只给屏幕看；body 留给下游解析（TTS 的音频 URL、OCR 的 usage.image_tokens）。
        # 只截 300 字符会把 URL 截断，记录下来的响应就无法再被程序消费。
        "excerpt": text[:EXCERPT_CHARS],
        "body": text[:BODY_CHARS],
        "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    record(args.out, row)

    ok = 200 <= status < 300
    print(f"[{args.capability}/{args.provider}] status={status} latency={latency_ms:.0f}ms ok={ok}")
    print(f"返回摘要：{text[:EXCERPT_CHARS]}")
    print(f"已追加到 {args.out}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
