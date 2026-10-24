"""种子数据：建一个最小可跑的本体（消化/普外片段）+ ICD-10 对齐表 + 一份样例资产。

与 ingest_asset 走同一条解析链路，保证三元组的 provenance 锚点真实存在——
否则决策链报告里每条证据都会被标成「未找到」，溯源完整率恒为 0。

用法：python seed.py [--reset]
"""
from __future__ import annotations

import sys
from pathlib import Path

import parsers
import store

D = lambda i, l: {"id": i, "type": "Disease", "label": l}
S = lambda i, l: {"id": i, "type": "Symptom", "label": l}
E = lambda i, l: {"id": i, "type": "Exam", "label": l}
DR = lambda i, l: {"id": i, "type": "Drug", "label": l}
P = lambda i, l: {"id": i, "type": "Department", "label": l}

ASSET_ID = "AST-2026-000137"
SAMPLE_PATH = Path(__file__).resolve().parent.parent / "data" / "samples" / "pathway_k27.md"

# (head, rel, tail, confidence, 锚点提示词) —— 提示词用于在样例文档里定位证据句
TRIPLES = [
    (D("R10.1", "上腹部痛"), "has_symptom", S("SYM-EPI", "上腹隐痛"), 0.9, "上腹隐痛"),
    (S("SYM-EPI", "上腹隐痛"), "diagnosed_by", D("K27", "消化性溃疡"), 0.78, "确诊依赖胃镜"),
    (D("K27", "消化性溃疡"), "requires_exam", E("EX-HP-BT", "幽门螺杆菌呼气试验"), 0.92, "幽门螺杆菌呼气试验"),
    (D("K27", "消化性溃疡"), "requires_exam", E("EX-GASTRO", "胃镜"), 0.9, "需要做胃镜检查"),
    (D("K27", "消化性溃疡"), "belongs_to_dept", P("DEP-GI", "消化内科"), 0.95, "消化性溃疡"),
    (DR("DRUG-IBU", "布洛芬"), "contraindicated_for", D("K27", "消化性溃疡"), 0.88, "禁用布洛芬"),
    (D("K27", "消化性溃疡"), "aligned_to_standard", D("ICD10-K27", "ICD-10 K27"), 0.99, ""),
    (S("SYM-EPI", "上腹隐痛"), "belongs_to_dept", P("DEP-GI", "消化内科"), 0.8, "上腹隐痛"),
    (D("K29", "胃炎"), "has_symptom", S("SYM-EPI", "上腹隐痛"), 0.7, "上腹隐痛"),
    (D("K29", "胃炎"), "requires_exam", E("EX-GASTRO", "胃镜"), 0.86, "胃镜检查"),
    (D("K29", "胃炎"), "requires_exam", E("EX-HP-BT", "幽门螺杆菌呼气试验"), 0.84, "幽门螺杆菌呼气试验"),
    (D("K29", "胃炎"), "belongs_to_dept", P("DEP-GI", "消化内科"), 0.9, "消化性溃疡"),
    (D("K21", "胃食管反流病"), "has_symptom", S("SYM-HEART", "烧心"), 0.85, "烧心"),
    (D("K21", "胃食管反流病"), "requires_exam", E("EX-GASTRO", "胃镜"), 0.8, "胃镜检查"),
    (D("K21", "胃食管反流病"), "belongs_to_dept", P("DEP-GI", "消化内科"), 0.88, "反酸"),
    (D("K21", "胃食管反流病"), "aligned_to_standard", D("ICD10-K21", "ICD-10 K21"), 0.99, ""),
    (D("K29", "胃炎"), "aligned_to_standard", D("ICD10-K29", "ICD-10 K29"), 0.99, ""),
]

ALIASES = [
    ("上腹部痛", "R10.1", "ICD-10", "Symptom", 0.95),
    ("上腹隐痛", "SYM-EPI", "local", "Symptom", 0.9),
    ("消化性溃疡", "K27", "ICD-10", "Disease", 0.98),
    ("胃溃疡", "K27", "ICD-10", "Disease", 0.9),
    ("胃炎", "K29", "ICD-10", "Disease", 0.95),
    ("胃食管反流", "K21", "ICD-10", "Disease", 0.9),
    ("烧心", "SYM-HEART", "local", "Symptom", 0.9),
    ("反酸", "SYM-HEART", "local", "Symptom", 0.88),
    ("幽门螺杆菌", "EX-HP-BT", "local", "Exam", 0.85),
    ("胃镜", "EX-GASTRO", "local", "Exam", 0.92),
    ("布洛芬", "DRUG-IBU", "local", "Drug", 0.95),
    ("消化内科", "DEP-GI", "local", "Department", 0.99),
]


def build_asset(conn) -> list[dict]:
    """按 ingest_asset 的同一套解析器生成资产卡片，锚点 id 里的文件名换成资产号。"""
    doc = parsers.parse(SAMPLE_PATH)
    if doc is None:
        raise SystemExit("样例文件缺失：" + str(SAMPLE_PATH))
    for a in doc.anchors:
        a["anchor_id"] = a["anchor_id"].replace(SAMPLE_PATH.stem, ASSET_ID)
    card = {
        "asset_id": ASSET_ID,
        "title": "消化性溃疡临床路径（2023 版）摘要",
        "modality": doc.modality,
        "source": {"type": "public_standard", "publisher": "国家卫生健康委", "path": str(SAMPLE_PATH)},
        "version": {"value": "2023", "captured_at": store.now(), "supersedes": None},
        "sensitivity": "public",
        "structure": {"blocks": len(doc.blocks), "anchors": len(doc.anchors),
                      "kinds": sorted({b.kind for b in doc.blocks})},
        "anchors": doc.anchors,
        "entities": parsers.guess_entities(doc),
        "kb_status": "ready",
        "ingested_by": "T2",
    }
    store.upsert_asset(conn, card)
    return doc.anchors


def pick_anchor(anchors: list[dict], hint: str) -> dict:
    if hint:
        for a in anchors:
            if hint in a.get("text", ""):
                return a
    return anchors[0]


def main(reset: bool = False) -> None:
    db = store.DB_PATH
    if reset and db.exists():
        db.unlink()
    conn = store.connect()
    for surface, code, scheme, etype, conf in ALIASES:
        conn.execute("INSERT OR REPLACE INTO alias (surface,code,scheme,entity_type,confidence) VALUES (?,?,?,?,?)",
                     (surface, code, scheme, etype, conf))
    conn.commit()

    anchors = build_asset(conn)

    n = 0
    for head, rel, tail, conf, hint in TRIPLES:
        a = pick_anchor(anchors, hint)
        if store.add_triple(conn, {
            "head": head, "rel": rel, "tail": tail, "confidence": conf,
            "provenance": {"asset_id": ASSET_ID, "anchor_id": a["anchor_id"]},
            "standard": {"scheme": "ICD-10", "code": head["id"]} if head["type"] == "Disease" else {},
        }, version="v0.9"):
            n += 1

    snap = store.snapshot(conn, "v0.9", "seed from opencmkg subset")
    print("seeded triples:", n, "aliases:", len(ALIASES), "anchors:", len(anchors))
    print("snapshot:", snap["version"], snap["triple_count"], snap["manifest_hash"])
    for a in anchors:
        print("  ", a["anchor_id"], "|", a["kind"], "|", a["text"][:48])
    conn.close()


if __name__ == "__main__":
    main("--reset" in sys.argv)
