#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""KG 手动测试入口：规则层 / LLM 层 / 科室遍历。

用法（仓库根目录）：
    python tools/kg/demo.py --check
    python tools/kg/demo.py --probe
    python tools/kg/demo.py 腿疼
    python tools/kg/demo.py "我腿疼" --llm
    python tools/kg/demo.py "我腿疼" --llm --trace
    python tools/kg/demo.py "我腿疼" --no-llm --age 68
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.adapters.kg.memory import MemoryGraphRepository  # noqa: E402
from backend.adapters.kg.selector import NodeSelector  # noqa: E402
from backend.adapters.llm import LlmConfig, LlmError, OpenAICompatibleLlm  # noqa: E402
from backend.domain.triage import reason_text, traverse  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="小暖陪诊 · KG 手动测试")
    parser.add_argument("text", nargs="?", default="我腿疼", help="患者主诉")
    parser.add_argument("--llm", action="store_true", help="启用 LLM 选节点")
    parser.add_argument("--no-llm", action="store_true", help="只走规则层")
    parser.add_argument("--age", type=int, default=None, help="患者年龄，用于儿科过滤")
    parser.add_argument("--trace", action="store_true", help="打印 LLM 工具调用轨迹")
    parser.add_argument("--check", action="store_true", help="只检查 LLM 配置")
    parser.add_argument("--probe", action="store_true", help="发一条最小请求，验证鉴权/网关")
    return parser


def print_config(config: LlmConfig) -> None:
    problems = config.validate()
    print("LLM 配置：")
    print(f"  enabled   = {config.enabled}")
    print(f"  model     = {config.model}")
    print(f"  base_url  = {config.base_url}")
    print(f"  api_key   = {'已配置' if config.api_key else '未配置'}")
    print(f"  timeout   = {config.timeout}")
    if problems:
        print("  问题      = " + "; ".join(problems))
    else:
        print("  问题      = 无")


def main() -> int:
    args = build_parser().parse_args()
    config = LlmConfig.from_env()

    if args.check:
        print_config(config)
        return 0 if not config.validate() else 2

    if args.probe:
        print_config(config)
        problems = config.validate()
        if problems:
            print("探测失败：配置不完整")
            return 2
        try:
            message = OpenAICompatibleLlm(config).chat(
                [{"role": "user", "content": "回复 ok"}], []
            )
        except LlmError as exc:
            print(f"探测失败：{exc}")
            if "insufficient_quota" in str(exc):
                print(
                    "提示：该网关对不在可用列表的模型也可能返回 insufficient_quota；"
                    "请确认 LLM_MODEL_FAST 与控制台支持的模型一致。"
                )
            return 2
        print(f"探测成功：{message}")
        return 0

    repo = MemoryGraphRepository.from_json(ROOT / "fixtures" / "kg" / "demo_graph.json")
    llm = None
    if args.llm:
        problems = config.validate()
        if problems:
            print_config(config)
            print("LLM 不可用，先修配置或改用 --no-llm。")
            return 2
        llm = OpenAICompatibleLlm(config)

    selector = NodeSelector(repo, llm)
    selection = selector.select(args.text, use_llm=not args.no_llm)

    print(f"输入：{args.text}")
    print(f"节点：{list(selection.nodes)}")
    print(f"来源：{selection.source}  耗时：{selection.elapsed_ms}ms")
    if selection.note:
        print(f"说明：{selection.note}")
    if args.trace and selection.trace:
        print("轨迹：")
        print(json.dumps(selection.trace, ensure_ascii=False, indent=2))

    if not selection.nodes:
        print("结果：没有可遍历的节点")
        return 0

    result = traverse(selection.nodes, repo, age=args.age)
    print(f"总票数：{result.total_votes}  置信度：{result.confidence}  enough：{result.enough}")
    if result.filtered_pediatric:
        print(f"已过滤儿科：{list(result.filtered_pediatric)}")
    for item in result.suggestions:
        evidence = "、".join(item.evidence)
        print(
            f"  - {item.department}  票数={item.votes}  "
            f"置信度={item.confidence}  依据={evidence}"
        )
    print(f"理由：{reason_text(result)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
