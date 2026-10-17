#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""红线回归检查：扫描面向用户的文案，确认禁用词出现次数为 0。

用法：
    python tools/check_guard_words.py

退出码：0 = 通过；1 = 命中禁用词
"""
from __future__ import annotations

import sys
from pathlib import Path

# 与 12-开发规范与测试规范 中的禁用词表保持一致
BANNED = [
    "没事的", "不严重", "不要紧", "我认为", "应该是", "肯定是",
    "你得的是", "建议您吃", "可以加量", "加一片", "不用去医院",
    "小毛病", "放心吧没事", "我诊断",
]

SCAN_DIRS = [Path("backend/domain/talk"), Path("frontend"), Path("device")]
EXTS = {".py", ".vue", ".js", ".ts", ".html", ".yaml", ".yml", ".json"}


def main() -> int:
    hits: list[tuple[Path, int, str, str]] = []
    for d in SCAN_DIRS:
        if not d.exists():
            continue
        for f in d.rglob("*"):
            if not f.is_file() or f.suffix not in EXTS:
                continue
            try:
                text = f.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for lineno, line in enumerate(text.splitlines(), 1):
                for w in BANNED:
                    if w in line:
                        hits.append((f, lineno, w, line.strip()[:100]))

    if not hits:
        print("红线回归通过：禁用词出现 0 次。")
        return 0

    print(f"红线回归失败：命中 {len(hits)} 处。")
    for f, lineno, w, snippet in hits:
        print(f"  {f}:{lineno}  禁用词「{w}」  {snippet}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
