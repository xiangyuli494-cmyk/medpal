#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""红线回归：扫描面向用户的文案，确认禁用词出现次数为 0。

词表来自 tools/guard_words.txt（唯一来源），不写死在脚本里。

用法：
    python tools/check_guard_words.py
    python tools/check_guard_words.py backend frontend device
    python tools/check_guard_words.py --words tools/guard_words.txt device

退出码：0 通过；1 命中；2 扫描异常（词表缺失或文件无法解码）
"""

from __future__ import annotations

import sys
from pathlib import Path

DEFAULT_WORDS = Path("tools/guard_words.txt")
DEFAULT_DIRS = [Path("backend/domain"), Path("frontend"), Path("device")]
EXTS = {".py", ".vue", ".js", ".ts", ".html", ".yaml", ".yml", ".json", ".md"}
SKIP_PARTS = {"node_modules", "dist", ".git", "__pycache__", ".venv", "build"}


def load_words(path: Path) -> list[str]:
    if not path.is_file():
        print(f"扫描异常：找不到词表 {path}", file=sys.stderr)
        raise SystemExit(2)
    words = []
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        words.append(line)
    if not words:
        print(f"扫描异常：词表 {path} 是空的", file=sys.stderr)
        raise SystemExit(2)
    return words


def read_text(path: Path) -> str | None:
    data = path.read_bytes()
    for enc in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return None


def main(argv: list[str]) -> int:
    words_path = DEFAULT_WORDS
    dirs: list[Path] = []
    args = argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--words" and i + 1 < len(args):
            words_path = Path(args[i + 1])
            i += 2
            continue
        dirs.append(Path(args[i]))
        i += 1
    if not dirs:
        dirs = DEFAULT_DIRS

    banned = load_words(words_path)
    hits: list[tuple[Path, int, str, str]] = []
    unreadable: list[Path] = []
    scanned = 0

    for d in dirs:
        if not d.exists():
            continue
        for f in d.rglob("*"):
            if not f.is_file() or f.suffix not in EXTS:
                continue
            if SKIP_PARTS & set(f.parts):
                continue
            text = read_text(f)
            if text is None:
                unreadable.append(f)
                continue
            scanned += 1
            for lineno, line in enumerate(text.splitlines(), 1):
                for w in banned:
                    if w in line:
                        hits.append((f, lineno, w, line.strip()[:100]))

    if unreadable:
        print("扫描异常：以下文件无法按 utf-8 / gb18030 解码：", file=sys.stderr)
        for f in unreadable:
            print(f"  {f}", file=sys.stderr)
        return 2

    if not hits:
        print(f"红线回归通过：词表 {len(banned)} 条，已扫描 {scanned} 个文件，禁用词出现 0 次。")
        return 0

    print(f"红线回归失败：已扫描 {scanned} 个文件，命中 {len(hits)} 处。")
    for f, lineno, w, snippet in hits:
        print(f"  {f}:{lineno}  禁用词「{w}」  {snippet}")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
