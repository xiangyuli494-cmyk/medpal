"""本体版本差分：把两版本体摆在一起，说清增了/删了/改了哪些知识。

对应任务卡 4.2「版本差分对外接口：增/删/改三类，人可读」。

────────────────────────────────────────────────────────────────
设计定稿（2026-10-28，T4 / Hcp1111）
────────────────────────────────────────────────────────────────

1. 输入：遵循 T2 的快照格式
   读 ontology_<version>.jsonl，每行一条三元组：
   {triple_id, head_id, rel, tail_id, confidence, asset_id, anchor_id}

2. 判等：用「业务键」而不是 triple_id
   signature(t) = (head_id, rel, tail_id)
   理由：triple_id 由 store.add_triple() 用 uuid4 随机生成，重建库
        （seed --reset / 换机重灌 / 重新抽取）后同一知识会拿到新 id。
        若以 id 判等，会把「没变」误报成「删一条 + 加一条」。

3. 「改」的判定：业务键相同，比较三个字段
   confidence（差值 > 1e-6）、anchor_id、standard。
   只比 confidence 是不够的：只换证据句就查不出来。

4. id 漂移：不算「改」，但要留痕（进 id_drift，不放进 modified）

5. 输出：结构与 store.diff_versions() 同形（added/removed/modified + counts）。
   字段按 ontology-schema.md §4.2 输出：head/tail 嵌套、锚点在 provenance 下。
   快照只有 id 级信息，schema 里的 type/label/standard/version_added 拿不到，
   缺的键不输出、不臆造（字段名仍集中在 to_record()）。
   schema v0 未定义「差分报告」一节，本格式由 T4 先定，已提请 T1 并入（候选 §4.4）。
   注意：removed 的可信度依赖 status='deprecated' 的落库实现——在 T2 实现
   废弃标记之前，正常流程下 removed 恒为空（见交接单「已知风险」）。

────────────────────────────────────────────────────────────────
边界
────────────────────────────────────────────────────────────────
- 不修改 agent/mcp-server/store.py（T2 的内核，只读不写）。
- 不 import store.diff_versions()：其判等键与快照摘要有已知缺陷，
  独立实现避免被绑定，同时用对照测试暴露两套结果的差异。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

CONFIDENCE_EPS = 1e-6
CHANGED_FIELDS = ("confidence", "anchor_id", "standard")


class DiffVersionNotFound(FileNotFoundError):
    """版本快照文件不存在。显式报错，不许静默返回空结果。"""


def _entity(row: dict, prefix: str) -> dict:
    """按 schema §4.2 拼 head / tail。

    快照只保证有 <prefix>_id；type / label 若将来由快照提供则自动带上，
    拿不到就不输出这个键——不臆造不存在的字段。
    """
    node = {"id": row.get(prefix + "_id")}
    if row.get(prefix + "_type"):
        node["type"] = row[prefix + "_type"]
    if row.get(prefix + "_label"):
        node["label"] = row[prefix + "_label"]
    return node


def to_record(row: dict) -> dict:
    """对外字段名的唯一出口，形状对齐 ontology-schema.md §4.2。

    快照只有 id 级信息，schema 里的 head.type / head.label / standard /
    version_added 需 join 实体表才能补齐，本模块没有那些数据，故缺省不输出。
    """
    record = {
        "triple_id": row.get("triple_id"),
        "head": _entity(row, "head"),
        "rel": row.get("rel"),
        "tail": _entity(row, "tail"),
        "confidence": row.get("confidence"),
        "provenance": {
            "asset_id": row.get("asset_id"),
            "anchor_id": row.get("anchor_id"),
        },
    }
    if row.get("standard") is not None:
        record["standard"] = row["standard"]
    if row.get("version_added") is not None:
        record["version_added"] = row["version_added"]
    return record


def _field_value(record: dict, field: str):
    """按对外结构取字段值：anchor_id 藏在 provenance 里，不是顶层键。"""
    if field == "anchor_id":
        return (record.get("provenance") or {}).get("anchor_id")
    return record.get(field)


def signature(row: dict) -> tuple[str, str, str]:
    """业务身份：头 + 关系 + 尾。数据库编号不参与判等。"""
    return (row["head_id"], row["rel"], row["tail_id"])


def load_version(path: str | Path) -> dict[tuple[str, str, str], dict]:
    """读一个版本快照，返回 {业务键: 行}。"""
    p = Path(path)
    if not p.is_file():
        raise DiffVersionNotFound("版本快照不存在：" + str(p))

    rows: dict[tuple[str, str, str], dict] = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            rows[signature(row)] = row
    return rows


def changed_fields(old: dict, new: dict) -> list[str]:
    """同一条知识，哪些字段变了。空列表表示真的没变。"""
    changed: list[str] = []
    try:
        delta = abs(float(old.get("confidence", 0)) - float(new.get("confidence", 0)))
    except (TypeError, ValueError):
        delta = 1.0
    if delta > CONFIDENCE_EPS:
        changed.append("confidence")
    if old.get("anchor_id") != new.get("anchor_id"):
        changed.append("anchor_id")
    if old.get("standard") != new.get("standard"):
        changed.append("standard")
    return changed


def diff_versions(old_path: str | Path, new_path: str | Path) -> dict:
    """比较两版快照，返回增/删/改三类结果。"""
    old_rows = load_version(old_path)
    new_rows = load_version(new_path)

    added = [to_record(new_rows[k]) for k in sorted(new_rows.keys() - old_rows.keys())]
    removed = [to_record(old_rows[k]) for k in sorted(old_rows.keys() - new_rows.keys())]

    modified: list[dict] = []
    id_drift: list[dict] = []
    for key in sorted(old_rows.keys() & new_rows.keys()):
        before, after = old_rows[key], new_rows[key]
        fields = changed_fields(before, after)
        if fields:
            modified.append(
                {
                    "head": {"id": key[0]},
                    "rel": key[1],
                    "tail": {"id": key[2]},
                    "changed_fields": fields,
                    "old": to_record(before),
                    "new": to_record(after),
                    "triple_id_old": before.get("triple_id"),
                    "triple_id_new": after.get("triple_id"),
                }
            )
        elif before.get("triple_id") != after.get("triple_id"):
            id_drift.append(
                {
                    "head": {"id": key[0]},
                    "rel": key[1],
                    "tail": {"id": key[2]},
                    "triple_id_old": before.get("triple_id"),
                    "triple_id_new": after.get("triple_id"),
                }
            )

    return {
        "old": Path(old_path).stem,
        "new": Path(new_path).stem,
        "counts": {
            "added": len(added),
            "removed": len(removed),
            "modified": len(modified),
        },
        "added": added,
        "removed": removed,
        "modified": modified,
        "id_drift": id_drift,
    }


def _label(record: dict) -> str:
    return str(record["head"]["id"]) + " -" + str(record["rel"]) + "-> " + str(record["tail"]["id"])


def _change_text(record: dict) -> str:
    parts = []
    for field in record["changed_fields"]:
        before = _field_value(record["old"], field)
        after = _field_value(record["new"], field)
        parts.append(field + ": " + str(before) + " → " + str(after))
    return "；".join(parts)


def render_report(diff: dict) -> str:
    """把结果渲染成人能读的中文报告（答辩 / 周报 / 交接单都能直接用）。"""
    counts = diff["counts"]
    total = counts["added"] + counts["removed"] + counts["modified"]
    head = diff["old"] + " → " + diff["new"] + "："

    if total == 0 and not diff["id_drift"]:
        return head + "无变化（新增 0、删除 0、修改 0）"

    lines = [
        head
        + "新增 "
        + str(counts["added"])
        + "、删除 "
        + str(counts["removed"])
        + "、修改 "
        + str(counts["modified"]),
        "",
    ]

    if diff["added"]:
        lines.append("【新增 " + str(counts["added"]) + " 条】")
        for row in diff["added"]:
            lines.append(
                "  + "
                + _label(row)
                + "  (置信度 "
                + str(row.get("confidence"))
                + "，依据 "
                + str(_field_value(row, "anchor_id"))
                + ")"
            )
        lines.append("")

    if diff["removed"]:
        lines.append("【删除 " + str(counts["removed"]) + " 条】")
        for row in diff["removed"]:
            lines.append(
                "  - " + _label(row) + "  (依据 " + str(_field_value(row, "anchor_id")) + ")"
            )
        lines.append("")

    if diff["modified"]:
        lines.append("【修改 " + str(counts["modified"]) + " 条】")
        for record in diff["modified"]:
            lines.append("  ~ " + _label(record))
            lines.append("      " + _change_text(record))
        lines.append("")

    if diff["id_drift"]:
        lines.append(
            "【编号漂移 " + str(len(diff["id_drift"])) + " 条（知识未变，数据库编号换了）】"
        )
        for record in diff["id_drift"]:
            lines.append(
                "  · "
                + _label(record)
                + "  "
                + str(record["triple_id_old"])
                + " → "
                + str(record["triple_id_new"])
            )
        lines.append("")

    return "\n".join(lines).rstrip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="本体版本差分：v0.9 → v1.0 增/删/改")
    parser.add_argument("--base", required=True, help="旧版快照 jsonl 路径")
    parser.add_argument("--target", required=True, help="新版快照 jsonl 路径")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)

    try:
        diff = diff_versions(args.base, args.target)
    except DiffVersionNotFound as exc:
        print("差分失败：" + str(exc), file=sys.stderr)
        return 1

    if args.format == "json":
        print(json.dumps(diff, ensure_ascii=False, indent=2))
    else:
        print(render_report(diff))
    return 0


if __name__ == "__main__":
    sys.exit(main())
