"""trace.json 校验与迁移工具 —— `agent/docs/trace-schema.md` 的执行体。

为什么要有这个脚本：schema 文档写在 Markdown 里，人手看不等于机器能验。
T3 的静态页、T6 的 CI 门禁、T2 的 trace 产出，三方都要一个「这份 trace 合不合 v1」的
唯一答案，答案只能来自代码，不能来自三个人的阅读理解。

用法：

    # 校验单份（骨架期方言也能校验，会提示需要 migrate）
    python tools/validate_trace.py tmp/trace.json

    # 校验数据库里最近 10 条真实 trace
    python tools/validate_trace.py --db mcp-server/data/medpal.db --limit 10

    # 把骨架期方言迁成 v1 并打印
    python tools/validate_trace.py tmp/trace.json --migrate

    # CI 门禁：不合格退出码 1
    python tools/validate_trace.py --db mcp-server/data/medpal.db --quiet

退出码：0 全部合格 / 1 有不合格 / 2 文件或依赖问题。
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path

try:
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover
    print("缺少 jsonschema：pip install jsonschema", file=sys.stderr)
    raise SystemExit(2)

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = Path(__file__).resolve().parent / "trace.schema.json"

# 骨架期方言 -> v1 的 op 改名表。walking-skeleton/1 的 op 是"层名"，v1 的 op 是"动作名"。
OP_RENAME = {
    "parse": "parse",
    "align_evidence": "align_evidence",
    "ingest": "ingest",
    "reason_2hop": "kg_query",  # 骨架期只跑两跳，v1 统一叫 kg_query，跳数放 in/out
    "conclude": "conclude",
}

# ref 与 op 的映射（docs §3.3）。骨架期 ref 必填，v1 起可由 op 推导。
REF_BY_OP = {
    "ingest": "STORE",
    "parse": "PARSE",
    "entity_extract": "EVIDENCE",
    "align_evidence": "EVIDENCE",
    "std_align": "EVIDENCE",
    "kg_query": "TRAVERSE",
    "reason_2hop": "TRAVERSE",
    "retrieve": "EVIDENCE",
    "conflict_check": "EVIDENCE",
    "conclude": "CONCLUDE",
    "skill_export": "CONCLUDE",
}

TRACE_ID_RE = re.compile(r"^TR-[0-9]{8}-[0-9A-F]{4}$")
TRIPLE_RE = re.compile(r"^T-[0-9a-f]{8}$")
ASSET_ANCHOR_RE = re.compile(r"^AST-[A-Za-z0-9][A-Za-z0-9-]*#[A-Za-z0-9._:\[\]-]+$")
BARE_ASSET_RE = re.compile(r"^AST-[A-Za-z0-9][A-Za-z0-9-]*$")


def load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def evidence_shape_errors(evidence) -> list[str]:
    """evidence 是「字符串数组」这件事必须硬卡。

    store.write_trace 对 evidence 只做 for e in s.get("evidence")，传字符串 "T-0f5bfa1d"
    会被按字符遍历，产出 9 条假证据、溯源完整率照算不误、报告照写 —— 静默产垃圾。
    JSON Schema 只能拦住类型，拦不住"看着像数组的元素"，所以这里再验一遍格式。
    """
    errs = []
    if isinstance(evidence, str):
        return ['evidence 是字符串，会被逐字符遍历；必须是数组，如 ["T-xxxxxxxx"]']
    for e in evidence or []:
        if not isinstance(e, str):
            errs.append("evidence 元素必须是字符串，收到 %r" % (e,))
        elif TRIPLE_RE.match(e) or ASSET_ANCHOR_RE.match(e) or BARE_ASSET_RE.match(e):
            continue
        else:
            errs.append(
                "evidence 元素格式非法：%r（只认 T-<8hex> 或 <asset_id>#<anchor_id>）" % (e,)
            )
    return errs


def validate(trace: dict, schema: dict | None = None) -> list[str]:
    schema = schema or load_schema()
    v = Draft202012Validator(schema)
    errs = []
    for e in sorted(v.iter_errors(trace), key=lambda x: list(x.absolute_path)):
        where = "/".join(str(p) for p in e.absolute_path) or "<root>"
        errs.append("%s: %s" % (where, e.message))
    for idx, s in enumerate(trace.get("steps") or []):
        if isinstance(s, dict):
            for msg in evidence_shape_errors(s.get("evidence")):
                errs.append("steps/%d/evidence: %s" % (idx, msg))
            # ref 与 op 同说一件事，写了就必须对得上。报告只渲染 op，
            # 所以 ref 写错永远没人发现——只能在这里卡。
            ref = s.get("ref")
            expect = REF_BY_OP.get(s.get("op", ""))
            if ref is not None and expect and ref != expect:
                errs.append(
                    "steps/%d/ref: op=%r 应为 ref=%r，实际 %r"
                    % (idx, s.get("op"), expect, ref)
                )
    # 步序严格递增：write_trace 不排序，乱序会让报告表格读起来像跳步
    seq = [s.get("i") for s in (trace.get("steps") or []) if isinstance(s, dict)]
    if all(isinstance(x, int) for x in seq) and seq != sorted(seq):
        errs.append("steps: i 必须严格递增，实际 %r" % (seq,))
    if len(seq) == len(set(seq)):
        pass
    elif all(isinstance(x, int) for x in seq):
        errs.append("steps: i 有重复，实际 %r" % (seq,))
    return errs


def derive_sources(trace: dict, conn=None) -> list[str]:
    """从 evidence 反推来源资产。

    两种形态分开处理：
      - `AST-...#anchor` —— 前缀就是 asset_id，直接切（不需查库）
      - `T-<8hex>` —— 要查 triple.asset_id（传了 conn 才能反推，不传就算不出来）
    不传 conn 时不猜：宁可从缺，也不把三元组 id 当资产 id 写进 sources。
    """
    out = []
    for s in trace.get("steps") or []:
        for e in s.get("evidence") or []:
            if not isinstance(e, str):
                continue
            aid = None
            if "#" in e:
                head = e.split("#")[0]
                if BARE_ASSET_RE.match(head):
                    aid = head
            elif TRIPLE_RE.match(e) and conn is not None:
                row = conn.execute(
                    "SELECT asset_id FROM triple WHERE triple_id=?", (e,)
                ).fetchone()
                if row:
                    aid = row[0] if not isinstance(row, sqlite3.Row) else row["asset_id"]
            if aid and aid not in out:
                out.append(aid)
    return sorted(out)


def migrate(trace: dict, sources_by_triple: dict | None = None) -> dict:
    """walking-skeleton/1 -> medpal-trace/1。

    只改结构不改语义：step->i、detail 保留、op 改名、ref 省略（由 op 推导）。
    schema 字段换成新值，其余字段原样搬运，conclusion 直接留在顶层。

    evidence 前缀归一：骨架期用源文件名当伪资产前缀（`pathway_k27#p1`），v1 只认
    AST- 开头的真实 asset_id，所以按 trace.asset.asset_id 替换前缀。锚点本身是否
    真实存在不做猜测——留给校验器判 unresolved，这比「迁移时悄悄改成凑数的锚点」诚实。
    """
    pseudo_asset = (trace.get("asset") or {}).get("asset_id")
    rehomed = 0

    def fix_ref(e: str) -> str:
        nonlocal rehomed
        if "#" not in e or BARE_ASSET_RE.match(e.split("#")[0]):
            return e
        if not pseudo_asset:
            return e
        rehomed += 1
        return "%s#%s" % (pseudo_asset, e.split("#", 1)[1])

    steps = []
    for n, s in enumerate(trace.get("steps") or [], start=1):
        if not isinstance(s, dict):
            continue
        op = OP_RENAME.get(s.get("op", ""), s.get("op", ""))
        item = {
            "i": s.get("i", s.get("step", n)),
            "op": op,
            "evidence": [fix_ref(e) for e in (s.get("evidence") or [])],
        }
        if "detail" in s:
            item["detail"] = s["detail"]
        if "in" in s:
            item["in"] = s["in"]
        if "out" in s:
            item["out"] = s["out"]
        steps.append(item)
    migrated = {
        "schema": "medpal-trace/1",
        "trace_id": trace.get("trace_id") or "TR-19700101-0000",
        "question": trace.get("question") or _question_from_asset(trace),
        "agent_version": trace.get("agent_version") or "walking-skeleton",
        "ontology_version": trace.get("ontology_version") or "v0.9",
        "created_at": trace.get("created_at") or "1970-01-01T00:00:00+08:00",
        "elapsed_ms": int(trace.get("elapsed_ms") or 0),
        "steps": steps,
        "gaps": list(trace.get("gaps") or []),
        "unresolved": list(trace.get("unresolved") or []),
        "trace_completeness": float(trace.get("trace_completeness") or 0.0),
    }
    if trace.get("conclusion"):
        migrated["conclusion"] = trace["conclusion"]
    if rehomed:
        migrated["gaps"] = list(migrated["gaps"]) + [
            "骨架期有 %d 条证据用文件名当资产前缀，迁移时已改挂 %s，锚点需按真实 blocks 重对"
            % (rehomed, pseudo_asset)
        ]
    srcs = derive_sources(migrated)
    if sources_by_triple:
        for s in migrated["steps"]:
            for e in s["evidence"]:
                aid = sources_by_triple.get(e)
                if aid and aid not in srcs:
                    srcs.append(aid)
    if srcs:
        migrated["sources"] = sorted(srcs)
    return migrated


def _question_from_asset(trace: dict) -> str:
    asset = trace.get("asset") or {}
    if asset.get("title"):
        return "（骨架期未记录问题）基于资产《%s》的两跳查询" % asset["title"]
    return "（骨架期未记录问题）"


def load_from_db(db: Path, limit: int) -> list[dict]:
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM trace ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    out = []
    for r in rows:
        t = {
            "schema": "medpal-trace/1",
            "trace_id": r["trace_id"],
            "question": r["question"],
            "agent_version": r["agent_version"],
            "ontology_version": r["ontology_version"],
            "created_at": r["created_at"],
            "elapsed_ms": r["elapsed_ms"],
            "steps": json.loads(r["steps_json"]),
            "gaps": json.loads(r["gaps_json"]),
        }
        # trace_completeness 不落库，按 store.write_trace 同一公式重算，
        # 保证「库里没有这个字段」和「库里能验这个字段」不是两套计算。
        cited, unresolved = _recount(conn, t["steps"])
        t["trace_completeness"] = round(1 - len(unresolved) / len(cited), 3) if cited else 1.0
        t["unresolved"] = unresolved
        srcs = derive_sources(t, conn)
        if srcs:
            t["sources"] = srcs
        out.append(t)
    conn.close()
    return out


def _recount(conn, steps) -> tuple[list[str], list[str]]:
    """复刻 store.py:526-534 的口径：按出现顺序去重 collected，再逐个查落点。"""
    cited: list[str] = []
    for s in steps:
        for e in (s.get("evidence") or []) if isinstance(s, dict) else []:
            if not isinstance(e, str):
                continue
            if e not in cited:
                cited.append(e)
    unresolved = []
    for e in cited:
        ok = False
        if e.startswith("T-"):
            ok = conn.execute("SELECT 1 FROM triple WHERE triple_id=?", (e,)).fetchone() is not None
        elif "#" in e:
            aid = e.split("#")[0]
            # 用下标取列：调用方可能传没设 row_factory 的连接（测试里就是），
            # 按列名取会 TypeError，而这里只要拿 anchors_json 一列。
            row = conn.execute("SELECT anchors_json FROM asset WHERE asset_id=?", (aid,)).fetchone()
            if row:
                raw = row[0] if not isinstance(row, sqlite3.Row) else row["anchors_json"]
                ok = any(a.get("anchor_id") == e for a in json.loads(raw or "[]"))
        else:
            ok = conn.execute("SELECT 1 FROM asset WHERE asset_id=?", (e,)).fetchone() is not None
        if not ok:
            unresolved.append(e)
    return cited, unresolved


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="校验 / 迁移 trace.json 到 medpal-trace/1")
    ap.add_argument("path", nargs="?", help="单份 trace.json 路径")
    ap.add_argument("--db", help="从 SQLite 里批量取 trace 校验")
    ap.add_argument("--limit", type=int, default=10, help="--db 时最多校验几条，默认 10")
    ap.add_argument("--migrate", action="store_true", help="把骨架期方言迁成 v1 并打印")
    ap.add_argument("--quiet", action="store_true", help="只输出结论行，CI 用")
    args = ap.parse_args(argv)

    schema = load_schema()
    cases: list[tuple[str, dict]] = []

    if args.path:
        p = Path(args.path)
        if not p.exists():
            print("找不到文件：%s" % p, file=sys.stderr)
            return 2
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            print("不是合法 JSON：%s" % e, file=sys.stderr)
            return 2
        if args.migrate:
            migrated = migrate(raw)
            print(json.dumps(migrated, ensure_ascii=False, indent=2))
            cases.append((str(p) + "（已迁移）", migrated))
        else:
            if raw.get("schema") != "medpal-trace/1":
                print(
                    "注意：schema=%r，不是 medpal-trace/1，用 --migrate 转换" % raw.get("schema"),
                    file=sys.stderr,
                )
            cases.append((str(p), raw))
    elif args.db:
        db = Path(args.db)
        if not db.exists():
            print("找不到数据库：%s" % db, file=sys.stderr)
            return 2
        for i, t in enumerate(load_from_db(db, args.limit)):
            cases.append(("%s #%d" % (db.name, i + 1), t))
    else:
        ap.print_help()
        return 2

    bad = 0
    for label, trace in cases:
        errs = validate(trace, schema)
        if errs:
            bad += 1
            print("❌ %s  %s" % (label, trace.get("trace_id")))
            for msg in errs:
                print("   - " + msg)
        elif not args.quiet:
            print(
                "✅ %s  %s  steps=%d  completeness=%s  sources=%s"
                % (
                    label,
                    trace.get("trace_id"),
                    len(trace.get("steps") or []),
                    trace.get("trace_completeness"),
                    ",".join(trace.get("sources") or []) or "—",
                )
            )
    if not args.quiet:
        print("\n%d/%d 合格" % (len(cases) - bad, len(cases)))
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
