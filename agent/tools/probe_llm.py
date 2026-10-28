"""模型通道自检：ASR / TTS / OCR / LLM 各打通一次。

对应赛题3 W1 任务 5.3（`agent/tools/probe_llm.py`，截止 10-27）。
它是 5.4 混合检索、5.7 OCR 落地与 T2 抽取调 LLM 的共同前置。

用法：
    export DASHSCOPE_API_KEY=sk-xxx        # 或从仓库根 .env.local 读
    python -m agent.tools.probe_llm        # 或 python agent/tools/probe_llm.py

输出四行 OK（或 FAIL），每行带耗时与估算成本，可直接贴进交接单。
"""
from __future__ import annotations

import base64
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE = "https://dashscope.aliyuncs.com"
MM = f"{BASE}/api/v1/services/aigc/multimodal-generation/generation"
TTS = f"{BASE}/api/v1/services/audio/tts/SpeechSynthesizer"
CHAT = f"{BASE}/compatible-mode/v1/chat/completions"

ROOT = Path(__file__).resolve().parents[2]


def key() -> str:
    k = os.environ.get("DASHSCOPE_API_KEY", "")
    if k:
        return k
    env = ROOT / ".env.local"
    if env.is_file():
        for line in env.read_text(encoding="utf-8"):
            if line.startswith("DASHSCOPE_API_KEY="):
                return line.split("=", 1)[1].strip()
    raise SystemExit("缺少 DASHSCOPE_API_KEY（环境变量或仓库根 .env.local）")


def post(url: str, body: dict, timeout: int = 120) -> tuple[dict, float]:
    req = urllib.request.Request(
        url, data=json.dumps(body, ensure_ascii=False).encode(),
        headers={"Authorization": f"Bearer {key()}", "Content-Type": "application/json"},
        method="POST")
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode()), (time.perf_counter() - t0) * 1000


def probe_asr() -> str:
    wavs = sorted((ROOT / "tools/probe/samples/asr").glob("*.wav"))
    if not wavs:
        return "FAIL  未找到 ASR 样本（tools/probe/samples/asr/*.wav）"
    b64 = base64.b64encode(wavs[0].read_bytes()).decode()
    d, ms = post(MM, {"model": "qwen3-asr-flash", "input": {"messages": [
        {"role": "user", "content": [{"audio": "data:audio/wav;base64," + b64}]}]}})
    text = d["output"]["choices"][0]["message"]["content"][0]["text"]
    tokens = d.get("usage", {}).get("input_tokens", 0)
    return f"OK    {ms:.0f}ms  tokens={tokens}  识别：{text[:24]}"


def probe_tts() -> str:
    text = "请到二楼检验科，出电梯往左走"
    d, ms = post(TTS, {"model": "qwen-audio-3.1-tts-flash",
                       "input": {"text": text, "voice": "longanhuan_v3.1",
                                 "format": "wav", "sample_rate": 16000}})
    url = d["output"]["audio"]["url"]
    cost = len(text) * 0.8 / 10000
    return f"OK    {ms:.0f}ms  {len(text)} 字  约 {cost:.4f} 元  url={'有' if url else '无'}"


def probe_ocr() -> str:
    imgs = sorted((ROOT / "tools/probe/samples/ocr").glob("05_*.png"))
    if not imgs:
        return "FAIL  未找到 OCR 样本（tools/probe/samples/ocr/05_*.png）"
    b64 = base64.b64encode(imgs[0].read_bytes()).decode()
    # 必须明确要 JSON 且禁止版面坐标，否则 qwen3.5-ocr 会回 rotate_rect 之类的布局数据
    prompt = (
        "只输出 JSON，不要代码块、不要解释、不要任何版面坐标："
        '{"doses":[{"drug":"","dose_value":"","dose_unit":""}]}；'
        "剂量数值与单位必须分开，图上没有的字段留空字符串。"
    )
    body = {"model": "qwen3.5-ocr", "input": {"messages": [
        {"role": "user", "content": [{"image": "data:image/png;base64," + b64},
                                     {"text": prompt}]}]}}
    d, ms = post(MM, body)
    out = d["output"]["choices"][0]["message"]["content"][0]["text"]
    out = re.sub(r"\s+", " ", out.strip())[:60]
    itok = d.get("usage", {}).get("image_tokens", 0)
    return f"OK    {ms:.0f}ms  image_tokens={itok}  摘录：{out}"


def probe_llm() -> str:
    d, ms = post(CHAT, {"model": "qwen-plus", "messages": [
        {"role": "user", "content": "只回答四个字：通道正常"}], "max_tokens": 16})
    content = d["choices"][0]["message"]["content"].strip()
    u = d.get("usage", {})
    in_tok, out_tok = u.get("prompt_tokens"), u.get("completion_tokens")
    return f"OK    {ms:.0f}ms  in={in_tok} out={out_tok}  回答：{content[:16]}"


def main() -> int:
    print(f"模型通道自检 · 根目录 {ROOT}")
    failed = 0
    probes = [("ASR", probe_asr), ("TTS", probe_tts),
              ("OCR", probe_ocr), ("LLM", probe_llm)]
    for name, fn in probes:
        try:
            line = fn()
        except urllib.error.HTTPError as e:
            line = f"FAIL  HTTP {e.code}  {e.read().decode()[:80]}"
        except Exception as e:  # noqa: BLE001
            line = f"FAIL  {type(e).__name__}: {e}"
        failed += line.startswith("FAIL")
        print(f"{name:4} {line}")
    print(f"\n结论：{'四项全通' if failed == 0 else str(failed) + ' 项失败'}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
