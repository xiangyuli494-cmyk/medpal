#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""从毕设数据库导出可复用、且不含个人信息的种子数据。

只导三类：检查项与院内方位、科室字典、排班样例。
**绝不导出**：user_user、user_doctor、aichat_registrationrecord、chat、checkpoints
（含手机号、姓名、病史、诊断）。

用法：
    python tools/legacy/extract_seed.py --sql "<毕设>/database/medical.sql"
    python tools/legacy/extract_seed.py --sql medical.sql --out fixtures/legacy

产物：
    fixtures/legacy/check_items.json    检查项目 + 部位 + 位置说明
    fixtures/legacy/departments.json    一级科室字典（含排班数量）
    fixtures/legacy/schedule_samples.json  排班样例（医生姓名已脱敏）
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

CHECK_ITEM_COLS = [
    "id",
    "jcflmc",
    "flxh",
    "jcxmxh",
    "jcxmmc",
    "bwmc",
    "wzsm",
    "wzid",
    "zysx",
    "create_time",
]
SCHEDULE_COLS = [
    "id",
    "yjksmc",
    "ejksmc",
    "sjksmc",
    "ysdm",
    "ysmc",
    "zcmc",
    "rq",
    "rs",
    "fybz",
    "dateindex",
    "create_time",
    "yjksdm",
    "yjpybm",
    "yspybm",
    "zcdm",
]


def read_sql(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def iter_tuples(segment: str):
    """解析 INSERT ... VALUES 后面的 (..),(..) 序列，处理转义与 NULL。"""
    start = segment.find("(")
    i = start
    n = len(segment)
    while i != -1 and i < n:
        i += 1
        fields: list[str | None] = []
        buf: list[str] = []
        in_str = False
        while i < n:
            c = segment[i]
            if in_str:
                if c == "\\":
                    buf.append(segment[i + 1])
                    i += 2
                    continue
                if c == "'":
                    if i + 1 < n and segment[i + 1] == "'":
                        buf.append("'")
                        i += 2
                        continue
                    in_str = False
                    i += 1
                    continue
                buf.append(c)
                i += 1
                continue
            if c == "'":
                in_str = True
                i += 1
                continue
            if c == ",":
                fields.append("".join(buf).strip())
                buf = []
                i += 1
                continue
            if c == ")":
                fields.append("".join(buf).strip())
                i += 1
                yield [None if f == "NULL" else f for f in fields]
                break
            buf.append(c)
            i += 1
        nxt = segment.find("(", i)
        i = nxt


def load_table(data: str, table: str, cols: list[str]) -> list[dict]:
    marker = "INSERT INTO " + "`" + table + "`" + " VALUES"
    idx = data.find(marker)
    if idx == -1:
        marker = "INSERT INTO " + table + " VALUES"
        idx = data.find(marker)
    if idx == -1:
        return []
    segment = data[idx + len(marker) :]
    end = segment.find(";\n")
    if end != -1:
        segment = segment[:end]
    rows = []
    for values in iter_tuples(segment):
        if len(values) != len(cols):
            continue
        rows.append(dict(zip(cols, values)))
    return rows


def mask_name(name: str) -> str:
    """医生姓名脱敏：稳定哈希后缀，便于同一人前后一致。"""
    if not name:
        return "医生-未知"
    digest = hashlib.sha1(name.encode("utf-8")).hexdigest()[:4]
    return "医生-" + digest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sql", required=True)
    parser.add_argument("--out", default="fixtures/legacy")
    parser.add_argument("--max-items", type=int, default=800)
    args = parser.parse_args()

    data = read_sql(Path(args.sql))

    items = load_table(data, "aichat_departmentcheckitem", CHECK_ITEM_COLS)
    schedules = load_table(data, "aichat_hospitalschedule", SCHEDULE_COLS)

    seen = set()
    check_items = []
    for row in items:
        name = (row.get("jcxmmc") or "").strip().rstrip("_").strip()
        place = (row.get("wzsm") or "").strip()
        if not name or not place:
            continue
        key = (name, place)
        if key in seen:
            continue
        seen.add(key)
        check_items.append(
            {
                "id": int(row["id"]) if row.get("id") else None,
                "category": row.get("jcflmc"),
                "item_code": row.get("jcxmxh"),
                "item_name": name,
                "body_part": row.get("bwmc"),
                "location": place,
            }
        )
        if len(check_items) >= args.max_items:
            break

    dept_count: dict[str, int] = {}
    doctor_title: dict[str, str] = {}
    for row in schedules:
        dept = (row.get("yjksmc") or "").strip()
        if dept:
            dept_count[dept] = dept_count.get(dept, 0) + 1
        doc = (row.get("ysmc") or "").strip()
        if doc:
            doctor_title[mask_name(doc)] = row.get("zcmc") or ""
    departments = [
        {"name": name, "schedule_rows": count}
        for name, count in sorted(dept_count.items(), key=lambda kv: -kv[1])
    ]

    sample_rows = []
    for row in schedules[:40]:
        sample_rows.append(
            {
                "dept": row.get("yjksmc"),
                "doctor": mask_name(row.get("ysmc") or ""),
                "title": row.get("zcmc"),
                "date": row.get("rq"),
                "total": int(row["rs"]) if row.get("rs") else 0,
                "remaining": int(row["fybz"]) if row.get("fybz") else 0,
            }
        )

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    payload = {
        "check_items": check_items,
        "departments": departments,
        "schedule_samples": sample_rows,
        "doctors": [{"alias": k, "title": v} for k, v in sorted(doctor_title.items())][:60],
    }
    (out / "check_items.json").write_text(
        json.dumps(check_items, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    (out / "departments.json").write_text(
        json.dumps(departments, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    (out / "schedule_samples.json").write_text(
        json.dumps(sample_rows, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    (out / "doctors.json").write_text(
        json.dumps(payload["doctors"], ensure_ascii=False, indent=1), encoding="utf-8"
    )

    print(f"检查项 {len(check_items)} 条，科室 {len(departments)} 个")
    print(f"排班样例 {len(sample_rows)} 条")
    print(f"输出目录：{out}")
    print("提示：本批数据不含姓名、手机号、病史、诊断，可直接进仓库。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
