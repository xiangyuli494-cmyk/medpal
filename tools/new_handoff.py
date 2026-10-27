#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""按模板生成一份模块交接单。

用法：
    python tools/new_handoff.py --module 领域模型 --owner T1 --week 1
    python tools/new_handoff.py --module device-ui --owner T4
"""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

TEMPLATE = Path("docs/handoff/模板.md")
OUT_DIR = Path("docs/handoff")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--module", required=True)
    parser.add_argument("--owner", required=True, help="T1 - T6")
    parser.add_argument("--week", default="1")
    args = parser.parse_args()

    if not TEMPLATE.is_file():
        print(f"找不到模板 {TEMPLATE}")
        return 2

    text = TEMPLATE.read_text(encoding="utf-8-sig")
    text = text.replace("{{模块}}", args.module)
    text = text.replace("{{工号}}", args.owner)
    text = text.replace("{{周次}}", args.week)
    text = text.replace("{{日期}}", date.today().isoformat())

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    target = OUT_DIR / f"W{args.week}-{args.owner}-{args.module}.md"
    if target.exists():
        print(f"已存在：{target}（要重写就先删掉）")
        return 1
    target.write_text(text, encoding="utf-8")
    print(f"已生成：{target}")
    print("接下来：把里面那几处说明文字换成你自己的话，再提交。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
