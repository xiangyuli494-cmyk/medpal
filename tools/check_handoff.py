#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""模块交接单检查：改了代码，就必须交一份自述。

规则：
1. 改了 backend/ frontend/ device/ tools/ 或任何 .py .vue .js .ts，必须在本 PR 里
   新增或修改 docs/handoff/W{周}-T{工号}-{模块}.md；
2. 交接单必须含四个小节且有实质内容：
   一句话说清它干什么 / 数据流 / 我改了什么 / 怎么验证的；
3. 文件名必须是 W数字-T数字-名字.md。

用法：
    python tools/check_handoff.py                        # 检查目录下全部交接单
    python tools/check_handoff.py --base origin/main     # CI：按 PR 改动检查
    python tools/check_handoff.py docs/handoff/W1-T1-领域模型.md

退出码：0 通过；1 不合格；2 无法检查
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HANDOFF_DIR = Path("docs/handoff")
SKIP_NAMES = {"README.md", "模板.md"}
CODE_PREFIXES = ("backend/", "frontend/", "device/", "tools/", ".github/")
CODE_SUFFIXES = (".py", ".vue", ".js", ".ts", ".tsx", ".jsx", ".ps1")
SECTIONS = {
    "一句话": "一句话说清它干什么",
    "数据流": "数据流",
    "我改了什么": "我改了什么（人工修改点）",
    "怎么验证": "怎么验证的",
}
MIN_CHARS = 20


def git(*args: str) -> str:
    # core.quotepath=false：否则中文/空格路径会被转义成 \345\210... 形式，匹配不到 docs/handoff/
    return subprocess.run(
        ["git", "-c", "core.quotepath=false", *args],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout


def changed_files(base: str) -> list[str]:
    try:
        out = git("diff", "--name-only", f"{base}...HEAD")
    except subprocess.CalledProcessError:
        # 浅克隆或缺少 merge-base 时退化为两点 diff，避免整条检查失效
        out = git("diff", "--name-only", f"{base}..HEAD")
    return [line.strip() for line in out.splitlines() if line.strip()]


def is_code(path: str) -> bool:
    return path.startswith(CODE_PREFIXES) or path.endswith(CODE_SUFFIXES)


def is_handoff(path: str) -> bool:
    p = Path(path)
    return p.parent.as_posix() == HANDOFF_DIR.as_posix() and p.name not in SKIP_NAMES


def sections_of(text: str) -> dict[str, str]:
    """把 markdown 拆成二级标题到内容的映射。"""
    result: dict[str, str] = {}
    current = None
    buffer: list[str] = []
    for line in text.splitlines():
        if line.startswith("## "):
            if current is not None:
                result[current] = "\n".join(buffer).strip()
            current = line[3:].strip()
            buffer = []
        elif current is not None:
            buffer.append(line)
    if current is not None:
        result[current] = "\n".join(buffer).strip()
    return result


def check_one(path: Path) -> list[str]:
    problems: list[str] = []
    name = path.name
    stem_parts = name[:-3].split("-") if name.endswith(".md") else []
    name_ok = (
        len(stem_parts) >= 3
        and stem_parts[0].startswith("W")
        and stem_parts[1].startswith("T")
    )
    if not name_ok:
        problems.append(f"{name}: 文件名应为 W周-T工号-模块.md")

    text = path.read_text(encoding="utf-8-sig")
    first = next((line for line in text.splitlines() if line.strip()), "")
    if not first.startswith("# 模块"):
        problems.append(f"{name}: 第一行标题应为「# 模块：<名称>」")

    body = sections_of(text)
    for key, label in SECTIONS.items():
        hit = next((v for k, v in body.items() if k.startswith(key)), None)
        if hit is None:
            problems.append(f"{name}: 缺少小节「## {label}」")
        elif len(hit.replace(" ", "").replace("\n", "")) < MIN_CHARS:
            problems.append(f"{name}: 小节「{label}」内容太短（至少 {MIN_CHARS} 字）")
    return problems


def all_handoff_files() -> list[Path]:
    if not HANDOFF_DIR.is_dir():
        return []
    return [p for p in HANDOFF_DIR.glob("*.md") if p.name not in SKIP_NAMES]


def main(argv: list[str]) -> int:
    args = argv[1:]
    base = None
    explicit: list[str] = []
    i = 0
    while i < len(args):
        if args[i] == "--base" and i + 1 < len(args):
            base = args[i + 1]
            i += 2
            continue
        explicit.append(args[i])
        i += 1

    try:
        if explicit:
            targets = [Path(p) for p in explicit]
        elif base:
            files = changed_files(base)
            targets = [Path(p) for p in files if is_handoff(p)]
            code = [p for p in files if is_code(p)]
            if code and not targets:
                print("交接单检查失败：本 PR 改了代码，但没有交 docs/handoff/ 下的自述。")
                print("  改动的代码文件：")
                for p in code[:10]:
                    print(f"    {p}")
                print("  做法：python tools/new_handoff.py --module <模块名> --owner <T1..T6>")
                return 1
        else:
            targets = all_handoff_files()

        if not targets:
            print("交接单检查通过：没有需要检查的文件。")
            return 0

        problems: list[str] = []
        for path in targets:
            if not path.is_file():
                problems.append(f"{path}: 文件不存在")
                continue
            problems.extend(check_one(path))

        if problems:
            print(f"交接单检查失败：{len(problems)} 处问题")
            for p in problems:
                print(f"  {p}")
            return 1

        print(f"交接单检查通过：{len(targets)} 份")
        for path in targets:
            print(f"  {path}")
        return 0
    except subprocess.CalledProcessError as exc:
        print(f"交接单检查无法进行：git 命令失败 {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))