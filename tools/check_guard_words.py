#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""红线回归检查：扫描面向用户的文案，确认禁用词出现次数为 0。

用法：
    python tools/check_guard_words.py

退出码：0 = 通过；1 = 命中禁用词；2 = 扫描异常
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

SCAN_DIRS = [Path("backend/domain"), Path("frontend"), Path("device")]
EXTS = {".py", ".vue", ".js", ".ts", ".html", ".yaml", ".yml", ".json", ".md"}
SKIP_PARTS = {"node_modules", "dist", ".git", "__pycache__", ".venv"}


def _read(path: Path) -> str | None:
    """读取文本。优先 utf-8-sig 以兼容带 BOM 的文件；失败则尝试 gb18030。"""
    data = path.read_bytes()
    for enc in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return None


def main() -> int:
    hits: list[tuple[Path, int, str, str]] = []
    scanned = 0
    unreadable: list[Path] = []

    for d in SCAN_DIRS:
        if not d.exists():
            continue
        for f in d.rglob("*"):
            if not f.is_file() or f.suffix not in EXTS:
                continue
            if SKIP_PARTS & set(f.parts):
                continue
            text = _read(f)
            if text is None:
                unreadable.append(f)
                continue
            scanned += 1
            for lineno, line in enumerate(text.splitlines(), 1):
                for w in BANNED:
                    if w in line:
                        hits.append((f, lineno, w, line.strip()[:100]))

    if unreadable:
        print("扫描异常：以下文件无法按 utf-8 / gb18030 解码：", file=sys.stderr)
        for f in unreadable:
            print(f"  {f}", file=sys.stderr)
        return 2

    if not hits:
        print(f"红线回归通过：已扫描 {scanned} 个文件，禁用词出现 0 次。")
        return 0

    print(f"红线回归失败：已扫描 {scanned} 个文件，命中 {len(hits)} 处。")
    for f, lineno, w, snippet in hits:
        print(f"  {f}:{lineno}  禁用词「{w}」  {snippet}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
