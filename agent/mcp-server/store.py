"""MedPal-Cog 存储层：SQLite 三元组库 + 资产台账 + 版本快照 + 决策链。

单文件、无外部依赖，可脱离 Nexent 单独 pytest。
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

CST = timezone(timedelta(hours=8))
DATA_DIR = Path(__file__).resolve().parent / "data"
DB_PATH = DATA_DIR / "medpal.db"
REPORT_DIR = Path(__file__).resolve().parent / "reports"

SCHEMA = """
CREATE TABLE IF NOT EXISTS asset (
    asset_id       TEXT PRIMARY KEY,
    title          TEXT NOT NULL,
    modality       TEXT NOT NULL,
    source_json    TEXT,
    version_json   TEXT,
    sensitivity    TEXT DEFAULT 'public',
    structure_json TEXT,
    anchors_json   TEXT,
    entities_json  TEXT,
    kb_status      TEXT DEFAULT 'pending',
    ingested_by    TEXT,
    created_at     TEXT
);
CREATE TABLE IF NOT EXISTS triple (
    triple_id       TEXT PRIMARY KEY,
    head_id         TEXT NOT NULL,
    head_type       TEXT NOT NULL,
    head_label      TEXT NOT NULL,
    rel             TEXT NOT NULL,
    tail_id         TEXT NOT NULL,
    tail_type       TEXT NOT NULL,
    tail_label      TEXT NOT NULL,
    confidence      REAL DEFAULT 0.8,
    asset_id        TEXT,
    anchor_id       TEXT,
    standard_json   TEXT,
    status          TEXT DEFAULT 'active',
    version_added   TEXT,
    version_removed TEXT
);
CREATE INDEX IF NOT EXISTS idx_triple_head ON triple(head_id, status);
CREATE INDEX IF NOT EXISTS idx_triple_tail ON triple(tail_id, status);
CREATE TABLE IF NOT EXISTS version (
    version       TEXT PRIMARY KEY,
    created_at    TEXT,
    triple_count  INTEGER,
    manifest_hash TEXT,
    note          TEXT,
    is_current    INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS trace (
    trace_id         TEXT PRIMARY KEY,
    question         TEXT,
    agent_version    TEXT,
    ontology_version TEXT,
    steps_json       TEXT,
    gaps_json        TEXT,
    elapsed_ms       INTEGER,
    created_at       TEXT
);
CREATE TABLE IF NOT EXISTS alias (
    surface     TEXT PRIMARY KEY,
    code        TEXT,
    scheme      TEXT,
    entity_type TEXT,
    confidence  REAL DEFAULT 0.9
);
CREATE TABLE IF NOT EXISTS pending_diff (
    diff_id    TEXT PRIMARY KEY,
    status     TEXT DEFAULT 'pending',
    payload    TEXT,
    created_at TEXT
);
"""


def now() -> str:
    return datetime.now(CST).isoformat(timespec="seconds")


def connect(db_path=None):
    path = Path(db_path) if db_path else DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def _row2card(row):
    return {
        "asset_id": row["asset_id"],
        "title": row["title"],
        "modality": row["modality"],
        "source": json.loads(row["source_json"] or "{}"),
        "version": json.loads(row["version_json"] or "{}"),
        "sensitivity": row["sensitivity"],
        "structure": json.loads(row["structure_json"] or "{}"),
        "anchors": json.loads(row["anchors_json"] or "[]"),
        "entities": json.loads(row["entities_json"] or "[]"),
        "kb": {"base": "med-text", "doc_id": row["asset_id"], "status": row["kb_status"]},
        "ingested_by": row["ingested_by"],
        "created_at": row["created_at"],
    }


# ---------- 资产 ----------


def upsert_asset(conn, card):
    aid = card.get("asset_id") or (
        "AST-" + datetime.now(CST).strftime("%Y") + "-" + uuid.uuid4().hex[:6]
    )
    conn.execute(
        "INSERT OR REPLACE INTO asset "
        "(asset_id,title,modality,source_json,version_json,sensitivity,"
        "structure_json,anchors_json,entities_json,kb_status,ingested_by,created_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            aid,
            card.get("title", ""),
            card.get("modality", "text"),
            json.dumps(card.get("source", {}), ensure_ascii=False),
            json.dumps(card.get("version", {}), ensure_ascii=False),
            card.get("sensitivity", "public"),
            json.dumps(card.get("structure", {}), ensure_ascii=False),
            json.dumps(card.get("anchors", []), ensure_ascii=False),
            json.dumps(card.get("entities", []), ensure_ascii=False),
            card.get("kb_status", "pending"),
            card.get("ingested_by", ""),
            card.get("created_at") or now(),
        ),
    )
    conn.commit()
    return aid


def list_assets(conn, modality=None, entity=None, limit=100):
    sql = "SELECT * FROM asset WHERE 1=1"
    args = []
    if modality:
        sql += " AND modality = ?"
        args.append(modality)
    if entity:
        sql += " AND entities_json LIKE ?"
        args.append("%" + entity + "%")
    sql += " ORDER BY created_at DESC LIMIT ?"
    args.append(int(limit))
    return [_row2card(r) for r in conn.execute(sql, args)]


def get_asset(conn, asset_id):
    row = conn.execute("SELECT * FROM asset WHERE asset_id = ?", (asset_id,)).fetchone()
    return _row2card(row) if row else None


# ---------- 三元组与版本 ----------


def add_triple(conn, t, version="v0.9"):
    dup = conn.execute(
        "SELECT triple_id, confidence FROM triple "
        "WHERE head_id=? AND rel=? AND tail_id=? AND status='active'",
        (t["head"]["id"], t["rel"], t["tail"]["id"]),
    ).fetchone()
    if dup:
        conn.execute(
            "UPDATE triple SET confidence = ? WHERE triple_id = ?",
            (max(float(t.get("confidence", 0.8)), dup["confidence"]), dup["triple_id"]),
        )
        conn.commit()
        return None
    tid = t.get("triple_id") or ("T-" + uuid.uuid4().hex[:8])
    prov = t.get("provenance", {})
    conn.execute(
        "INSERT INTO triple "
        "(triple_id,head_id,head_type,head_label,rel,tail_id,tail_type,tail_label,"
        "confidence,asset_id,anchor_id,standard_json,status,version_added,version_removed) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,NULL)",
        (
            tid,
            t["head"]["id"],
            t["head"]["type"],
            t["head"]["label"],
            t["rel"],
            t["tail"]["id"],
            t["tail"]["type"],
            t["tail"]["label"],
            float(t.get("confidence", 0.8)),
            prov.get("asset_id"),
            prov.get("anchor_id"),
            json.dumps(t.get("standard", {}), ensure_ascii=False),
            "active",
            version,
        ),
    )
    conn.commit()
    return tid


def _triple_out(row):
    return {
        "triple_id": row["triple_id"],
        "head": {"id": row["head_id"], "type": row["head_type"], "label": row["head_label"]},
        "rel": row["rel"],
        "tail": {"id": row["tail_id"], "type": row["tail_type"], "label": row["tail_label"]},
        "confidence": row["confidence"],
        "provenance": {"asset_id": row["asset_id"], "anchor_id": row["anchor_id"]},
        "standard": json.loads(row["standard_json"] or "{}"),
        "version_added": row["version_added"],
    }


def neighbors(conn, node_ids, rel_filter=None):
    if not node_ids:
        return []
    marks = ",".join("?" * len(node_ids))
    sql = (
        "SELECT * FROM triple WHERE status='active' AND (head_id IN ("
        + marks
        + ") OR tail_id IN ("
        + marks
        + "))"
    )
    args = list(node_ids) + list(node_ids)
    if rel_filter:
        sql += " AND rel IN (" + ",".join("?" * len(rel_filter)) + ")"
        args += list(rel_filter)
    return conn.execute(sql, args).fetchall()


def kg_query(conn, seeds, max_hops=2, rel_filter=None, limit=20):
    """从种子实体出发做多跳广度遍历，返回带 provenance 的路径。"""
    seeds = [s.strip() for s in seeds if s and s.strip()]
    if not seeds:
        return {"ok": False, "reason": "no_seed", "hint": "种子实体为空，先做实体归一"}
    resolved, unresolved = [], []
    for s in seeds:
        # 先过别名表（同义词/ICD 编码都在这里），再退回标签精确匹配；
        # 头部命中不了就试尾部，否则「消化内科」这类只出现在尾端的节点永远召不回。
        code = resolve_entity(conn, s) or s
        hit = conn.execute(
            "SELECT head_id FROM triple WHERE status='active' "
            "AND (head_id=? OR head_label=?) LIMIT 1",
            (code, s),
        ).fetchone()
        if not hit:
            hit = conn.execute(
                "SELECT tail_id FROM triple WHERE status='active' "
                "AND (tail_id=? OR tail_label=?) LIMIT 1",
                (code, s),
            ).fetchone()
        if hit:
            resolved.append(hit[0])
        else:
            unresolved.append(s)
        # 一个种子可能同时压着别名节点和标准节点（如「胃镜」→ EX-GASTRO），把能命中的都放进去
        if code != s:
            extra = conn.execute(
                "SELECT head_id FROM triple WHERE status='active' AND head_id=? LIMIT 1", (s,)
            ).fetchone()
            if extra and extra[0] not in resolved:
                resolved.append(extra[0])

    paths = []
    seen = set()
    for start in resolved:
        frontier = [[start]]
        for _hop in range(max(1, int(max_hops))):
            nxt = []
            for path in frontier:
                for row in neighbors(conn, [path[-1]], rel_filter):
                    other = row["tail_id"] if row["head_id"] == path[-1] else row["head_id"]
                    if other in path:
                        continue
                    key = (start, other, row["triple_id"])
                    if key in seen:
                        continue
                    seen.add(key)
                    new_path = path + [other]
                    nxt.append(new_path)
                    steps = []
                    for a, b in zip(new_path, new_path[1:]):
                        r = conn.execute(
                            "SELECT * FROM triple WHERE status='active' AND "
                            "((head_id=? AND tail_id=?) OR (head_id=? AND tail_id=?)) LIMIT 1",
                            (a, b, b, a),
                        ).fetchone()
                        if r:
                            # 下游（评测、Skill、报告）要直接读 rel / 两端，这里一次给全，
                            # 免得再按 edge 字符串反解析。
                            steps.append(
                                {
                                    "triple_id": r["triple_id"],
                                    "edge": r["head_label"]
                                    + " -["
                                    + r["rel"]
                                    + "]-> "
                                    + r["tail_label"],
                                    "rel": r["rel"],
                                    "head_id": r["head_id"],
                                    "head_label": r["head_label"],
                                    "head_type": r["head_type"],
                                    "tail_id": r["tail_id"],
                                    "tail_label": r["tail_label"],
                                    "tail_type": r["tail_type"],
                                    "provenance": {
                                        "asset_id": r["asset_id"],
                                        "anchor_id": r["anchor_id"],
                                    },
                                    "confidence": r["confidence"],
                                }
                            )
                    score = round(sum(s["confidence"] for s in steps) / max(1, len(steps)), 3)
                    paths.append(
                        {
                            "nodes": new_path,
                            "hops": len(new_path) - 1,
                            "steps": steps,
                            "provenance": [s["provenance"] for s in steps],
                            "score": score,
                        }
                    )
            frontier = nxt
            if not frontier:
                break
    paths.sort(key=lambda p: (-p["hops"], -p["score"]))
    cur = current_version(conn)
    return {
        "ok": bool(paths),
        "version": cur["version"] if cur else None,
        "resolved": resolved,
        "unresolved": unresolved,
        "paths": paths[: int(limit)],
        "reason": None if paths else "no_path",
    }


def snapshot(conn, version, note=""):
    rows = conn.execute(
        "SELECT triple_id,head_id,rel,tail_id,confidence,asset_id,anchor_id FROM triple "
        "WHERE status='active' ORDER BY triple_id"
    ).fetchall()
    payload = "\n".join(
        r["triple_id"]
        + "|"
        + r["head_id"]
        + "|"
        + r["rel"]
        + "|"
        + r["tail_id"]
        + "|"
        + "%.3f" % r["confidence"]
        for r in rows
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
    conn.execute("UPDATE version SET is_current = 0")
    conn.execute(
        "INSERT OR REPLACE INTO version "
        "(version,created_at,triple_count,manifest_hash,note,is_current) "
        "VALUES (?,?,?,?,?,1)",
        (version, now(), len(rows), digest, note),
    )
    conn.commit()
    path = DATA_DIR / ("ontology_" + version + ".jsonl")
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(dict(r), ensure_ascii=False) + "\n")
    return {
        "version": version,
        "triple_count": len(rows),
        "manifest_hash": digest,
        "snapshot_path": str(path),
        "created_at": now(),
    }


def current_version(conn):
    row = conn.execute("SELECT * FROM version WHERE is_current = 1").fetchone()
    return dict(row) if row else None


def diff_versions(conn, old, new):
    def load(v):
        p = DATA_DIR / ("ontology_" + v + ".jsonl")
        if not p.exists():
            return {}
        out = {}
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                d = json.loads(line)
                out[d["triple_id"]] = (d["head_id"], d["rel"], d["tail_id"], d["confidence"])
        return out

    a, b = load(old), load(new)
    added = [{"triple_id": k, "signature": list(b[k])} for k in sorted(b.keys() - a.keys())]
    removed = [{"triple_id": k, "signature": list(a[k])} for k in sorted(a.keys() - b.keys())]
    modified = [
        {"triple_id": k, "old": list(a[k]), "new": list(b[k])}
        for k in sorted(a.keys() & b.keys())
        if a[k][:3] != b[k][:3] or abs(a[k][3] - b[k][3]) > 1e-6
    ]
    return {
        "old": old,
        "new": new,
        "added": added,
        "removed": removed,
        "modified": modified,
        "counts": {"added": len(added), "removed": len(removed), "modified": len(modified)},
    }


# ---------- 对齐 ----------


def align(conn, text):
    t = (text or "").strip()
    if not t:
        return {"ok": False, "reason": "empty_input"}
    row = conn.execute("SELECT * FROM alias WHERE surface = ?", (t,)).fetchone()
    how = "exact"
    if not row:
        row = conn.execute(
            "SELECT * FROM alias WHERE ? LIKE '%' || surface || '%' "
            "ORDER BY LENGTH(surface) DESC LIMIT 1",
            (t,),
        ).fetchone()
        how = "contains"
    if not row:
        return {
            "ok": False,
            "reason": "unmapped",
            "input": t,
            "hint": "加入待对齐队列，人工补 alias_map 后重跑",
        }
    return {
        "ok": True,
        "input": t,
        "match": how,
        "scheme": row["scheme"],
        "code": row["code"],
        "entity_type": row["entity_type"],
        "confidence": row["confidence"],
    }


def resolve_entity(conn, text):
    hit = conn.execute(
        "SELECT head_id FROM triple WHERE head_label = ? LIMIT 1", (text,)
    ).fetchone()
    if hit:
        return hit["head_id"]
    a = align(conn, text)
    return a.get("code") if a.get("ok") else None


# ---------- 决策链 ----------


def _evidence_exists(conn, ref):
    ref = str(ref)
    if ref.startswith("T-"):
        return (
            conn.execute("SELECT 1 FROM triple WHERE triple_id = ?", (ref,)).fetchone() is not None
        )
    if "#" in ref:
        aid = ref.split("#")[0]
        row = conn.execute("SELECT anchors_json FROM asset WHERE asset_id = ?", (aid,)).fetchone()
        if not row:
            return False
        return any(a.get("anchor_id") == ref for a in json.loads(row["anchors_json"] or "[]"))
    return conn.execute("SELECT 1 FROM asset WHERE asset_id = ?", (ref,)).fetchone() is not None


def _ref_str(e):
    """证据引用统一成字符串：三元组直接给 id，文档证据给 "asset_id#anchor_id"。
    kg_query 的 provenance 是 {asset_id, anchor_id} 结构，写决策链前必须先摊平，
    否则报告里无法逐条核对，也会在 join 时报 TypeError。"""
    if isinstance(e, dict):
        if e.get("triple_id"):
            return str(e["triple_id"])
        if e.get("anchor_id"):
            return (
                str(e["anchor_id"])
                if not e.get("asset_id")
                else "%s#%s" % (e["asset_id"], str(e["anchor_id"]).split("#")[-1])
            )
        return str(e)
    return str(e)


def write_trace(conn, question, steps, agent_version="v1.0", elapsed_ms=0, gaps=None):
    tid = "TR-" + datetime.now(CST).strftime("%Y%m%d") + "-" + uuid.uuid4().hex[:4].upper()
    cur = current_version(conn)
    onto = cur["version"] if cur else "v0.9"
    conn.execute(
        "INSERT INTO trace "
        "(trace_id,question,agent_version,ontology_version,steps_json,gaps_json,"
        "elapsed_ms,created_at) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (
            tid,
            question,
            agent_version,
            onto,
            json.dumps(steps, ensure_ascii=False),
            json.dumps(gaps or [], ensure_ascii=False),
            int(elapsed_ms),
            now(),
        ),
    )
    conn.commit()

    cited = []
    for s in steps:
        for e in s.get("evidence", []) or []:
            ref = _ref_str(e)
            if ref not in cited:
                cited.append(ref)
    unresolved = [e for e in cited if not _evidence_exists(conn, e)]
    # 没有可引证据时（拒答题）溯源完整率记为 1.0：结论是「超出覆盖范围」，
    # 本身不依赖证据，不构成不可追溯。报告里会显式写「证据数 0」以示区分。
    completeness = round(1 - len(unresolved) / len(cited), 3) if cited else 1.0

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report = REPORT_DIR / (tid + ".md")
    lines = [
        "# 决策链报告 " + tid,
        "",
        "- 问题：" + question,
        "- 智能体版本：" + agent_version,
        "- 本体版本：" + onto,
        "- 生成时间：" + now(),
        "- 证据数：" + str(len(cited)) + ("（无引用，拒答类结论）" if not cited else ""),
        "- 溯源完整率：" + str(completeness),
        "",
        "## 决策链",
        "",
        "| # | 操作 | 输入 | 输出 | 证据 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for s in steps:
        lines.append(
            "| {} | {} | {} | {} | {} |".format(
                s.get("i"),
                s.get("op"),
                str(s.get("in", "")),
                str(s.get("out", "")),
                ", ".join(_ref_str(e) for e in (s.get("evidence", []) or [])) or "—",
            )
        )
    lines += ["", "## 证据清单", ""]
    for e in cited:
        lines.append("- " + e + (" ✅" if e not in unresolved else " ❌ 未找到"))
    if gaps:
        lines += ["", "## 缺口", ""] + ["- " + g for g in gaps]
    report.write_text("\n".join(lines), encoding="utf-8")

    return {
        "ok": True,
        "trace_id": tid,
        "version": onto,
        "report_path": str(report),
        "evidence_count": len(cited),
        "trace_completeness": completeness,
        "unresolved": unresolved,
    }


def get_trace(conn, trace_id):
    row = conn.execute("SELECT * FROM trace WHERE trace_id = ?", (trace_id,)).fetchone()
    if not row:
        return None
    return {
        "trace_id": row["trace_id"],
        "question": row["question"],
        "agent_version": row["agent_version"],
        "ontology_version": row["ontology_version"],
        "steps": json.loads(row["steps_json"]),
        "gaps": json.loads(row["gaps_json"]),
        "elapsed_ms": row["elapsed_ms"],
        "created_at": row["created_at"],
    }
