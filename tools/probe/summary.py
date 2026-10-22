"""把 results.jsonl 聚合成选型对比表所需的数字。

用法：
    python tools/probe/summary.py
    python tools/probe/summary.py --json      # 给机器读，便于贴进表格

只统计 status == 200 的记录；失败的请求保留在原始文件里，但不参与平均值，
因为把 401/400 的往返时间混进延迟均值会让对比失去意义。
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

DEFAULT_IN = "tools/probe/results.jsonl"

# 官方价（华北2 北京，抓取 2026-10-20，来源见 docs/specs/ai-selection.md §10.1）
ASR_PRICE_PER_SECOND = 0.00022
TTS_PRICE_PER_CHAR = 0.8 / 10000
OCR_PRICE_INPUT_PER_TOKEN = 0.5 / 1_000_000
OCR_PRICE_OUTPUT_PER_TOKEN = 2 / 1_000_000


def load(path: Path) -> list[dict]:
    if not path.is_file():
        raise SystemExit(f"找不到 {path}；先跑 tools/probe/probe.py 生成记录")
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def cost_of(capability: str, body: dict) -> float:
    """按返回体里的 usage 算这一条的单价，不用估算值。"""
    usage = body.get("usage") or {}
    if capability == "asr":
        return usage.get("seconds", 0) * ASR_PRICE_PER_SECOND
    if capability == "tts":
        return usage.get("characters", 0) * TTS_PRICE_PER_CHAR
    if capability == "ocr":
        tokens_in = usage.get("input_tokens", 0) + usage.get("image_tokens", 0)
        tokens_out = usage.get("output_tokens", 0)
        return tokens_in * OCR_PRICE_INPUT_PER_TOKEN + tokens_out * OCR_PRICE_OUTPUT_PER_TOKEN
    return 0.0


def summarize(rows: list[dict]) -> list[dict]:
    result: list[dict] = []
    for capability in ("asr", "tts", "ocr"):
        ok = [r for r in rows if r.get("capability") == capability and r.get("status") == 200]
        if not ok:
            result.append({"capability": capability, "success": 0})
            continue
        latencies = sorted(r["latency_ms"] for r in ok)
        last = json.loads(ok[-1]["body"]) if ok[-1].get("body") else {}
        result.append(
            {
                "capability": capability,
                "success": len(ok),
                "provider": ok[-1].get("provider", ""),
                "model": ok[-1].get("model", ""),
                "latency_min": round(latencies[0], 1),
                "latency_median": round(statistics.median(latencies), 1),
                "latency_max": round(latencies[-1], 1),
                "usage": last.get("usage", {}),
                "cost_last": round(cost_of(capability, last), 6),
            }
        )
    return result


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="聚合探针结果")
    parser.add_argument("--in", dest="src", default=DEFAULT_IN)
    parser.add_argument("--json", action="store_true", help="输出 JSON，便于贴进文档")
    args = parser.parse_args(argv[1:])

    rows = load(Path(args.src))
    stats = summarize(rows)
    if args.json:
        print(json.dumps(stats, ensure_ascii=False, indent=2))
        return 0

    total = len(rows)
    ok = sum(1 for r in rows if r.get("status") == 200)
    print(f"记录 {total} 条，成功 {ok} 条（失败记录不参与延迟统计）\n")
    for item in stats:
        if not item["success"]:
            print(f"{item['capability'].upper():4} 无成功记录")
            continue
        print(
            f"{item['capability'].upper():4} {item['success']:>2} 次 | "
            f"延迟 min {item['latency_min']:.0f} / 中位 {item['latency_median']:.0f} / "
            f"max {item['latency_max']:.0f} ms | 最近一条 {item['cost_last']:.6f} 元"
        )
        print(f"     usage {json.dumps(item['usage'], ensure_ascii=False)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
