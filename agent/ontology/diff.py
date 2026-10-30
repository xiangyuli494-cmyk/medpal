"""本体版本差分：把两版本体摆在一起，说清增了/删了/改了哪些知识。

对应任务卡 4.2「版本差分对外接口：增/删/改三类，人可读」。

────────────────────────────────────────────────────────────────
设计定稿
────────────────────────────────────────────────────────────────

1. 输入：遵循 T2 的快照格式
   读 ontology_<version>.jsonl，每行一条三元组：
   {triple_id, head_id, rel, tail_id, confidence, asset_id, anchor_id}

2. 身份：以 ontology-schema.md §4.1 的主键 triple_id 为准
   增 / 删 / 改都按 triple_id 判定，与 schema 的字段表一致：
   triple_id 是主键，head_id / rel / tail_id 是内容。
   业务键 (head_id, rel, tail_id) 不承担身份，只做「对账」：
   schema §8 第 3 条把 (head, rel, tail) 定为判重键，说明同一条知识
   在库里只能有一行；因此若新版出现一个陌生 triple_id，而它的业务键
   在旧版里存在，唯一解释是这条知识被重新编号了，而不是删一条加一条。
   这类情况进 id_drift（编号漂移），不计入 added / removed。
   这样两种上游实现都能算对：id 稳定时 id_drift 为空；id 重新生成时
   也不会把「没变」误报成「全删全加」。

3. 「改」的判定：triple_id 相同，逐字段比对，只比「两侧快照都带」的字段
   候选字段 = confidence（差值 > 1e-6）、anchor_id、standard，
   以及 head_id / rel / tail_id（同一个 id 下这三个变了，是语义变更，
   不能因为「id 没变」就当成没改）。
   【输入受限】store.snapshot() 只导出 7 列
   （triple_id/head_id/rel/tail_id/confidence/asset_id/anchor_id），
   所以 standard 目前两侧都没有，自动不参与比对（见 §5）。

4. 编号漂移：不算「改」，但要留痕（进 id_drift，不放进 modified）
   若一条知识既换了编号、内容又变了，则 id_drift 与 modified 各记一条，
   两个事实都不隐瞒。

5. 输出：结构与 store.diff_versions() 同形（added/removed/modified + counts）。
   字段按 ontology-schema.md §4.2 输出：head/tail 嵌套、锚点在 provenance 下。
   快照只有 id 级信息，schema 里的 type/label/version_added 拿不到，
   缺的键不输出、不臆造（字段名仍集中在 to_record()）。
   结果里额外给 identity 与 compared_fields：身份用的是什么、本次实际比了
   哪几个字段，报告末尾也写一行，避免「报无变化」被误读成「所有字段都没变」。
   schema v0（2026-10-29 冻结）未定义「差分报告」一节，
   本格式由 T4 先定，待 schema v1 增补（候选 §4.4）。
   注意两处输入缺口，均不属本模块能修：
   - removed 依赖 status='deprecated' 落库，而 snapshot() 只导 status='active'
     的行——T2 补废弃实现之前，正常流程下 removed 恒为空。
   - standard / status / version_removed 不在快照里，schema §10 要求 T4 读它们，
     实际读不到；已记入交接单「已知风险」，待快照补列。

────────────────────────────────────────────────────────────────
边界
────────────────────────────────────────────────────────────────
- 不修改 agent/mcp-server/store.py（T2 的内核，只读不写）。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

CONFIDENCE_EPS = 1e-6
IDENTITY = "triple_id"
CANDIDATE_FIELDS = ("confidence", "anchor_id", "standard", "head_id", "rel", "tail_id")


class DiffVersionNotFound(FileNotFoundError):
    """版本快照文件不存在。显式报错，不许静默返回空结果。"""


class DiffVersionInvalid(ValueError):
    """快照内容坏了：缺 triple_id，或同一文件里编号重复。"""


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


def _field_value(record: dict, field: str) -> object:
    """按对外结构取字段值：anchor_id 藏在 provenance 里、head/tail 是嵌套对象。"""
    if field == "anchor_id":
        return (record.get("provenance") or {}).get("anchor_id")
    if field == "head_id":
        return (record.get("head") or {}).get("id")
    if field == "tail_id":
        return (record.get("tail") or {}).get("id")
    return record.get(field)


def signature(row: dict) -> tuple[str, str, str]:
    """业务键 (head, rel, tail)。只用于对账，不承担身份。"""
    return (row["head_id"], row["rel"], row["tail_id"])


def load_version(path: str | Path) -> list[dict]:
    """读一个版本快照，按文件顺序返回全部行。"""
    p = Path(path)
    if not p.is_file():
        raise DiffVersionNotFound("版本快照不存在：" + str(p))

    rows: list[dict] = []
    for lineno, line in enumerate(p.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        row = json.loads(line)
        if not row.get("triple_id"):
            raise DiffVersionInvalid(str(p) + " 第 " + str(lineno) + " 行缺 triple_id")
        rows.append(row)
    return rows


def index_by_id(rows: list[dict]) -> dict[str, dict]:
    """按 schema §4.1 的主键建索引。重号等于快照损坏，直接报错。"""
    out: dict[str, dict] = {}
    for row in rows:
        tid = row["triple_id"]
        if tid in out:
            raise DiffVersionInvalid("triple_id 重复：" + str(tid))
        out[tid] = row
    return out


def comparable_fields(old_rows: list[dict], new_rows: list[dict]) -> list[str]:
    """两侧快照都带、且至少有一行出现过的候选字段。

    快照格式是外部给的（store.snapshot() 只导 7 列），不比不存在的字段，
    免得留下「永远不触发」的死判据——那比不检测更危险。
    """
    seen: set[str] = set()
    for rows in (old_rows, new_rows):
        for row in rows:
            seen.update(row.keys())
    return [f for f in CANDIDATE_FIELDS if f in seen]


def changed_fields(old: dict, new: dict, fields: list[str] | None = None) -> list[str]:
    """同一条知识（同一 triple_id），哪些字段变了。空列表表示真的没变。"""
    changed: list[str] = []
    for field in CANDIDATE_FIELDS if fields is None else fields:
        if field == "confidence":
            try:
                delta = abs(float(old.get("confidence", 0)) - float(new.get("confidence", 0)))
            except (TypeError, ValueError):
                delta = 1.0
            if delta > CONFIDENCE_EPS:
                changed.append("confidence")
            continue
        if old.get(field) != new.get(field):
            changed.append(field)
    return changed


def _drift_record(before: dict, after: dict) -> dict:
    return {
        "head": {"id": after.get("head_id")},
        "rel": after.get("rel"),
        "tail": {"id": after.get("tail_id")},
        "triple_id_old": before.get("triple_id"),
        "triple_id_new": after.get("triple_id"),
    }


def diff_versions(old_path: str | Path, new_path: str | Path) -> dict:
    """比较两版快照，返回增/删/改三类结果。"""
    old_rows = load_version(old_path)
    new_rows = load_version(new_path)
    cmp_fields = comparable_fields(old_rows, new_rows)

    old_by_id = index_by_id(old_rows)
    new_by_id = index_by_id(new_rows)
    old_by_sig = {signature(row): row for row in old_rows}

    added: list[dict] = []
    id_drift: list[dict] = []
    renamed_old_ids: set[str] = set()
    renumbered: list[tuple[dict, dict]] = []

    for tid in sorted(new_by_id.keys() - old_by_id.keys()):
        after = new_by_id[tid]
        before = old_by_sig.get(signature(after))
        if before is not None and before["triple_id"] not in new_by_id:
            # 同一条知识、新编号：算编号漂移，不算删一条加一条
            renamed_old_ids.add(before["triple_id"])
            id_drift.append(_drift_record(before, after))
            renumbered.append((before, after))
        else:
            added.append(to_record(after))

    removed = [
        to_record(old_by_id[tid])
        for tid in sorted((old_by_id.keys() - new_by_id.keys()) - renamed_old_ids)
    ]

    modified: list[dict] = []
    common_ids = sorted(old_by_id.keys() & new_by_id.keys())
    pairs = [(old_by_id[tid], new_by_id[tid]) for tid in common_ids]
    for before, after in pairs + renumbered:
        changed = changed_fields(before, after, cmp_fields)
        if changed:
            modified.append(
                {
                    "triple_id": after.get("triple_id"),
                    "triple_id_old": before.get("triple_id"),
                    "triple_id_new": after.get("triple_id"),
                    "head": {"id": after.get("head_id")},
                    "rel": after.get("rel"),
                    "tail": {"id": after.get("tail_id")},
                    "changed_fields": changed,
                    "old": to_record(before),
                    "new": to_record(after),
                }
            )

    return {
        "old": Path(old_path).stem,
        "new": Path(new_path).stem,
        "identity": IDENTITY,
        "counts": {
            "added": len(added),
            "removed": len(removed),
            "modified": len(modified),
        },
        "added": added,
        "removed": removed,
        "modified": modified,
        "compared_fields": cmp_fields,
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


def _scope_note(fields: list[str]) -> str:
    """报告末尾的诚实声明：身份用什么、本次到底比了什么、什么没比。"""
    if not fields:
        return ""
    missing = [f for f in CANDIDATE_FIELDS if f not in fields]
    note = "（身份：" + IDENTITY + "；比对字段：" + "、".join(fields)
    if missing:
        note += "；" + "、".join(missing) + " 不在快照中，本次未比对"
    return "\n\n" + note + "）"


def render_report(diff: dict) -> str:
    """把结果渲染成人能读的中文报告（答辩 / 周报 / 交接单都能直接用）。"""
    counts = diff["counts"]
    total = counts["added"] + counts["removed"] + counts["modified"]
    head = diff["old"] + " → " + diff["new"] + "："
    scope = _scope_note(diff.get("compared_fields") or [])

    if total == 0 and not diff["id_drift"]:
        return head + "无变化（新增 0、删除 0、修改 0）" + scope

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

    return "\n".join(lines).rstrip() + scope


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
    except DiffVersionInvalid as exc:
        print("差分失败：快照内容不合法（" + str(exc) + "）", file=sys.stderr)
        return 1

    if args.format == "json":
        print(json.dumps(diff, ensure_ascii=False, indent=2))
    else:
        print(render_report(diff))
    return 0


if __name__ == "__main__":
    sys.exit(main())
