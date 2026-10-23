"""Walking Skeleton —— 赛题3 最小可通电主线。

一条命令跑完全链路，每层只做最细一件事：

    python -m agent.skeleton --in agent/data/samples/pathway_k27.md --out tmp/trace.json

    解析(.md 按空行切段) -> 资产入库(SQLite 单文件) -> 本体(硬编码实体与关系)
      -> 两跳遍历 -> 决策链 trace.json(step / evidence / ref)

刻意不做：PDF、OCR、表格识别、MySQL、版本差分、多跳、置信度校准、可视化、Docker。
每一样都是后面"加粗一根骨头"时的单点改动，不是现在。

只用标准库，装了 Python 3.10+ 就能跑。
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path

ASSET_ID = "AST-2026-000137"
SCHEMA_VERSION = "walking-skeleton/1"

# ---------------------------------------------------------------- 1. 解析


def parse_markdown(path: Path) -> dict:
    """按空行切段。标题单独成一个 block。不做版面分析。"""
    stem = path.stem
    raw = path.read_text(encoding="utf-8")
    title = stem
    blocks = []
    n = 0
    for chunk in re.split(r"\n\s*\n", raw):
        body = []
        for line in chunk.strip().splitlines():
            if line.lstrip().startswith("#"):
                if line.startswith("# "):
                    title = line.lstrip("#").strip()
                continue          # 标题只做定位，不进正文
            if line.strip():
                body.append(line)
        if not body:
            continue
        n += 1
        blocks.append({"loc": "p" + str(n), "text": "\n".join(body)})
    return {
        "title": title,
        "modality": "text/markdown",
        "stem": stem,
        "blocks": blocks,
        "anchors": [stem + "#" + b["loc"] for b in blocks],
    }

# ---------------------------------------------------------------- 2. 本体（硬编码）

ONTOLOGY = [
    # (head, rel, tail, confidence, 证据提示词)
    ("SYM-EPI", "diagnosed_by", "K27", 0.78, "确诊依赖胃镜"),
    ("SYM-EPI", "belongs_to_dept", "DEP-GI", 0.80, "上腹部痛"),
    ("K27", "requires_exam", "EX-GASTRO", 0.90, "胃镜检查"),
    ("K27", "requires_exam", "EX-HP-BT", 0.92, "幽门螺杆菌呼气试验"),
    ("K27", "belongs_to_dept", "DEP-GI", 0.95, "消化性溃疡"),
    ("DRUG-IBU", "contraindicated_for", "K27", 0.88, "禁用布洛芬"),
    ("K29", "has_symptom", "SYM-EPI", 0.70, "上腹隐痛"),
    ("K29", "requires_exam", "EX-GASTRO", 0.86, "胃镜检查"),
    ("K29", "belongs_to_dept", "DEP-GI", 0.90, "胃炎"),
    ("K21", "has_symptom", "SYM-HEART", 0.85, "烧心"),
    ("K21", "requires_exam", "EX-GASTRO", 0.80, "胃镜检查"),
    ("K21", "belongs_to_dept", "DEP-GI", 0.88, "反流"),
]

LABELS = {
    "SYM-EPI": ("Symptom", "上腹隐痛"),
    "SYM-HEART": ("Symptom", "烧心"),
    "K27": ("Disease", "消化性溃疡"),
    "K29": ("Disease", "胃炎"),
    "K21": ("Disease", "胃食管反流病"),
    "EX-GASTRO": ("Exam", "胃镜"),
    "EX-HP-BT": ("Exam", "幽门螺杆菌呼气试验"),
    "DEP-GI": ("Department", "消化内科"),
    "DRUG-IBU": ("Drug", "布洛芬"),
}

# ---------------------------------------------------------------- 3. 证据锚定


def anchor_of(blocks: list, hint: str):
    """找到第一段含提示词的 block，返回 loc。找不到返回 None（溯源断链）。"""
    for b in blocks:
        if hint and hint in b["text"]:
            return b["loc"]
    return None

# ---------------------------------------------------------------- 4. 存储


def build_store(db_path: Path, asset: dict, triples: list) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path)
    con.executescript(
        """
        DROP TABLE IF EXISTS asset;
        DROP TABLE IF EXISTS triple;
        CREATE TABLE asset (asset_id TEXT PRIMARY KEY, title TEXT, modality TEXT,
                            blocks INTEGER, anchors INTEGER);
        CREATE TABLE triple (head TEXT, rel TEXT, tail TEXT,
                             confidence REAL, anchor TEXT);
        """
    )
    con.execute(
        "INSERT INTO asset VALUES (?,?,?,?,?)",
        (ASSET_ID, asset["title"], asset["modality"],
         len(asset["blocks"]), len(asset["anchors"])),
    )
    con.executemany(
        "INSERT INTO triple VALUES (?,?,?,?,?)",
        [(h, r, t, c, a) for h, r, t, c, _hint, a in triples],
    )
    con.commit()
    con.close()

# ---------------------------------------------------------------- 5. 两跳遍历


def two_hop(start: str, triples: list, depth: int = 2) -> dict:
    """无向 BFS，最多两跳。返回 {节点: (路径, 累积置信度, 末段关系)}。"""
    adj = {}
    for h, r, t, c, _hint, _a in triples:
        adj.setdefault(h, []).append((t, r, c))
        adj.setdefault(t, []).append((h, "~" + r, c))

    found = {}
    frontier = [(start, [start], 1.0)]
    for _ in range(depth):
        nxt = []
        for node, path, conf in frontier:
            for nb, rel, c in adj.get(node, []):
                if nb in path:
                    continue
                np = path + [nb]
                nc = round(conf * c, 4)
                if nb not in found or found[nb][1] < nc:
                    found[nb] = (np, nc, rel)
                nxt.append((nb, np, nc))
        frontier = nxt
    return found

# ---------------------------------------------------------------- 6. 主流程


def run(in_path: Path, out_path: Path, db_path: Path) -> dict:
    steps = []

    asset = parse_markdown(in_path)
    steps.append({
        "step": 1, "op": "parse",
        "detail": asset["modality"] + " -> " + str(len(asset["blocks"])) + " blocks",
        "evidence": asset["anchors"][:1], "ref": "PARSE",
    })

    triples = []
    unresolved = []
    for h, r, t, c, hint in ONTOLOGY:
        loc = anchor_of(asset["blocks"], hint)
        if loc is None:
            unresolved.append(h + " -" + r + "-> " + t)
        triples.append((h, r, t, c, hint, loc))

    all_anchors = [asset["stem"] + "#" + t[5] for t in triples if t[5]]
    steps.append({
        "step": 2, "op": "align_evidence",
        "detail": str(len(triples)) + " triples, " + str(len(unresolved)) + " 断链",
        "evidence": all_anchors, "ref": "EVIDENCE",
    })

    build_store(db_path, asset, triples)
    steps.append({
        "step": 3, "op": "ingest",
        "detail": "asset " + ASSET_ID + " + " + str(len(triples)) + " triples -> " + db_path.name,
        "evidence": [ASSET_ID], "ref": "STORE",
    })

    start = "SYM-EPI"
    reached = two_hop(start, triples, depth=2)
    steps.append({
        "step": 4, "op": "reason_2hop",
        "detail": "从 " + start + " 出发两跳，到达 " + str(len(reached)) + " 个实体",
        "evidence": all_anchors[:3], "ref": "TRAVERSE",
    })

    dept_votes = {}
    for node, (_p, conf, _r) in reached.items():
        if LABELS.get(node, ("", ""))[0] == "Department":
            dept_votes[node] = round(dept_votes.get(node, 0.0) + conf, 4)
    depts = [{"id": k, "label": LABELS[k][1], "score": v}
             for k, v in sorted(dept_votes.items(), key=lambda kv: -kv[1])]

    diseases = sorted(n for n in reached if LABELS.get(n, ("", ""))[0] == "Disease")
    exams = sorted(n for n in reached if LABELS.get(n, ("", ""))[0] == "Exam")

    ev_by_entity = {}
    for h, _r, t, _c, _hint, loc in triples:
        if loc:
            a = asset["stem"] + "#" + loc
            ev_by_entity.setdefault(h, []).append(a)
            ev_by_entity.setdefault(t, []).append(a)

    def ev(ids):
        acc = []
        for i in ids:
            acc.extend(ev_by_entity.get(i, []))
        return sorted(set(acc))

    top = depts[0]["id"] if depts else None
    steps.append({
        "step": 5, "op": "conclude",
        "detail": "科室=" + (depts[0]["label"] if depts else "无")
                  + " 疾病=" + str(len(diseases)) + " 检查=" + str(len(exams)),
        "evidence": ev([top] if top else []), "ref": "CONCLUDE",
    })

    for s in steps:
        s["evidence"] = sorted(set(s["evidence"]))

    # 溯源完整率 = 有真实证据锚点的三元组 / 三元组总数。
    # 文档里找不到证据句，这里就会掉下来 —— 这是"可溯源"唯一的硬指标。
    completeness = round(len(all_anchors) / len(triples), 4) if triples else 0.0

    trace = {
        "schema": SCHEMA_VERSION,
        "asset": {
            "asset_id": ASSET_ID,
            "title": asset["title"],
            "modality": asset["modality"],
            "blocks": len(asset["blocks"]),
            "anchors": len(asset["anchors"]),
        },
        "ontology": {"entities": len(LABELS), "triples": len(triples)},
        "query": {"start": start, "depth": 2},
        "steps": steps,
        "conclusion": {
            "department": depts[0]["label"] if depts else None,
            "department_id": top,
            "department_score": depts[0]["score"] if depts else 0.0,
            "diseases": diseases,
            "exams": exams,
            "evidence": ev([top] if top else []),
        },
        "unresolved": sorted(unresolved),
        "trace_completeness": completeness,
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(trace, ensure_ascii=False, indent=2), encoding="utf-8")
    return trace


def main(argv=None) -> int:
    root = Path(__file__).resolve().parent.parent
    ap = argparse.ArgumentParser(description="Walking Skeleton：一条命令跑完赛题3 最小主线")
    ap.add_argument("--in", dest="inp",
                    default=str(root / "agent/data/samples/pathway_k27.md"))
    ap.add_argument("--out", dest="out", default=str(root / "tmp/trace.json"))
    ap.add_argument("--db", dest="db", default=str(root / "tmp/skeleton.db"))
    a = ap.parse_args(argv)

    t = run(Path(a.inp), Path(a.out), Path(a.db))
    print("OK  " + str(len(t["steps"])) + " steps | 科室=" + str(t["conclusion"]["department"])
          + " | 疾病=" + str(len(t["conclusion"]["diseases"]))
          + " | 检查=" + str(len(t["conclusion"]["exams"]))
          + " | 溯源完整率=" + str(t["trace_completeness"]))
    print("->  " + str(Path(a.out)))
    if t["unresolved"]:
        print("WARN 断链 " + str(len(t["unresolved"])) + " 条: " + ", ".join(t["unresolved"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
