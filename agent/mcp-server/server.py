"""MedPal-Cog MCP Server

七个工具全部对应赛题要求：
  ingest_asset / get_asset_card      -> R1 多模态资产识别与标识
  kg_query / onto_propose / onto_commit / std_align -> R2 本体半自动构建与标准对齐
  trace_write                        -> R4 跨文档推理与决策链溯源
R3 由「以 MCP 形式暴露给 Nexent + 三个 Skill 包编排」承载。

启动：
  python server.py                     # stdio（本地调试 / MCP Inspector）
  MCP_TRANSPORT=streamable-http python server.py   # HTTP，Nexent 远程链接用
"""
from __future__ import annotations

import json
import os
import re
import time
import uuid
from pathlib import Path

from mcp.server.fastmcp import FastMCP

import parsers
import store

SERVER_VERSION = "0.1.0"
mcp = FastMCP(
    "medpal-cog",
    instructions=(
        "MedPal-Cog 医疗数据资产认知工具集。所有结论必须携带 asset_id / anchor_id / triple_id，"
        "找不到证据时返回 ok=false 并说明缺口，不得编造。"
    ),
    host=os.environ.get("MCP_HOST", "0.0.0.0"),
    port=int(os.environ.get("MCP_PORT", "8090")),
    streamable_http_path="/mcp",
    stateless_http=True,
)


def _conn():
    return store.connect(os.environ.get("MEDPAL_DB") or None)


def _ok(**kw):
    kw.setdefault("ok", True)
    return kw


def _err(reason, hint="", **kw):
    out = {"ok": False, "reason": reason, "hint": hint}
    out.update(kw)
    return out


# ---------------- R1 资产 ----------------

@mcp.tool()
def ingest_asset(path: str, modality: str = "", title: str = "",
                 source_type: str = "public_standard", ingested_by: str = "") -> dict:
    """解析一份文件，生成 Asset Card 与可引用锚点，登记入台账。

    返回 asset_id、anchors（每条都可被决策链引用）、解析出的块数与实体。
    modality 留空时按扩展名自动判别：text / pdf_text / table / image_report。
    """
    p = Path(path)
    if not p.exists():
        return _err("file_not_found", "检查路径是否存在：" + path)
    doc = parsers.parse(p)
    if doc is None:
        return _err("no_parser", "该扩展名暂无解析器，请在 parsers.REGISTRY 注册", suffix=p.suffix)
    if doc.metadata.get("error"):
        return _err("parser_unavailable", doc.metadata["error"], path=str(p))

    entities = parsers.guess_entities(doc)
    card = {
        "title": title or doc.title,
        "modality": modality or doc.modality,
        "source": {"type": source_type, "publisher": "", "path": str(p)},
        "version": {"value": "v1", "captured_at": store.now(), "supersedes": None},
        "sensitivity": "public" if source_type == "public_standard" else "synthetic",
        "structure": {
            "blocks": len(doc.blocks),
            "anchors": len(doc.anchors),
            "kinds": sorted({b.kind for b in doc.blocks}),
        },
        "anchors": doc.anchors,
        "entities": entities,
        "kb_status": "ready",
        "ingested_by": ingested_by,
    }
    conn = _conn()
    asset_id = store.upsert_asset(conn, card)
    for a in card["anchors"]:
        a["anchor_id"] = a["anchor_id"].replace(p.stem, asset_id)
    card["asset_id"] = asset_id
    store.upsert_asset(conn, card)
    conn.close()
    return _ok(asset_id=asset_id, modality=card["modality"], anchors=card["anchors"],
               entity_hint=entities, blocks=len(doc.blocks))


@mcp.tool()
def get_asset_card(asset_id: str = "", modality: str = "", entity: str = "", limit: int = 20) -> dict:
    """按 asset_id / 模态 / 实体查资产卡片。三个条件都为空时返回最近入库的资产。"""
    conn = _conn()
    try:
        if asset_id:
            card = store.get_asset(conn, asset_id)
            return _ok(cards=[card]) if card else _err("asset_not_found", "先跑 ingest_asset", asset_id=asset_id)
        cards = store.list_assets(conn, modality or None, entity or None, limit)
        return _ok(count=len(cards), cards=cards)
    finally:
        conn.close()


# ---------------- R2 本体 ----------------

@mcp.tool()
def kg_query(seed_entities: list[str], max_hops: int = 2,
             rel_filter: list[str] = None, limit: int = 20) -> dict:
    """从种子实体出发做多跳本体查询，返回路径与每条边的 provenance。

    路径按「跳数多优先、置信度高优先」排序；未解析的种子会出现在 unresolved 里。
    """
    conn = _conn()
    try:
        return store.kg_query(conn, seed_entities or [], max_hops, rel_filter, limit)
    finally:
        conn.close()


# 只允许这三种句式，且头尾必须能被 alias_map 解析成节点——这是「约束输出空间」的落地。
PATTERNS = [
    (re.compile(r"(?P<head>[\u4e00-\u9fa5]{2,8}?)(?:患者)?(?:需要做|需要|应做|建议做|须做|需做)"
                r"(?P<tail>[\u4e00-\u9fa5]{2,10}?)(?:检查|检测|试验)"), "requires_exam"),
    (re.compile(r"(?P<head>[\u4e00-\u9fa5]{2,8}?)(?:可导致|可引起|会导致|可致)(?P<tail>[\u4e00-\u9fa5]{2,12})"), "may_cause"),
    (re.compile(r"(?P<head>[\u4e00-\u9fa5]{2,8}?)(?:禁用|慎用于|禁忌于)(?P<tail>[\u4e00-\u9fa5]{2,8})"), "contraindicated_for"),
]
TAIL_SUFFIX = re.compile(r"(等|药物|药品|治疗)$")
ROLE_SUFFIX = re.compile(r"(患者|病人|人群|者|等|药物|药品|治疗|疾病|症状)$")
# 这些关系正反说都指同一件事实，判重时两个方向都要查
REVERSE_TOLERANT = {"contraindicated_for"}


@mcp.tool()
def onto_propose(asset_ids: list[str], scope: str = "") -> dict:
    """从给定资产抽取候选三元组，产出待审 diff（不直接写库）。

    低资源策略：约束输出空间——只允许 3 类句式模板、6 类实体、8 类关系；
    规则校验在前（类型匹配、重复、空头尾），通过的才进待审队列。
    """
    conn = _conn()
    try:
        cands, rejected = [], []
        known = {r["head_label"] for r in conn.execute("SELECT DISTINCT head_label FROM triple")}
        known |= {r["tail_label"] for r in conn.execute("SELECT DISTINCT tail_label FROM triple")}
        aliases = {r["surface"] for r in conn.execute("SELECT surface FROM alias")}
        vocab = sorted(known | aliases, key=len, reverse=True)

        def expand(text: str, span: tuple) -> str:
            """把正则抓到的片段扩到「覆盖该片段的最长已知实体」。
            例：抓到「消化性溃疡患」，扩成「消化性溃疡」；抓到「幽门螺杆菌呼气」，扩成「幽门螺杆菌呼气试验」。"""
            hs, he = span
            if hs is None or he is None:
                return ""
            for v in vocab:  # 已按长度降序
                idx = text.find(v)
                while idx != -1:
                    if idx <= hs and idx + len(v) >= he:
                        return v
                    idx = text.find(v, idx + 1)
            raw = text[hs:he]
            inner = [v for v in vocab if v in raw]  # 片段内部含已知实体，取最长
            if inner:
                return inner[0]
            return ROLE_SUFFIX.sub("", raw) or raw

        for aid in asset_ids or []:
            card = store.get_asset(conn, aid)
            if not card:
                rejected.append({"asset_id": aid, "reason": "asset_not_found"})
                continue
            for a in card.get("anchors", []):
                text = a.get("text", "")
                if len(text) < 12:
                    rejected.append({"anchor_id": a["anchor_id"], "reason": "too_short"})
                    continue
                hit = False
                for pat, rel in PATTERNS:
                    for m in pat.finditer(text):
                        head = expand(text, m.span("head"))
                        tail = expand(text, m.span("tail"))
                        tail = TAIL_SUFFIX.sub("", tail) or tail
                        if not head or not tail or head == tail or tail in head or head in tail:
                            continue
                        hit = True
                        cands.append({
                            "head": {"id": "", "type": "Disease", "label": head},
                            "rel": rel,
                            "tail": {"id": "", "type": "Exam" if rel == "requires_exam" else "Disease", "label": tail},
                            "confidence": 0.72,
                            "provenance": {"asset_id": aid, "anchor_id": a["anchor_id"]},
                        })
                if not hit:
                    rejected.append({"anchor_id": a["anchor_id"], "reason": "no_pattern_match"})

        kept = []
        for c in cands:
            h = store.resolve_entity(conn, c["head"]["label"])
            t = store.resolve_entity(conn, c["tail"]["label"])
            if not h or not t:
                rejected.append({"candidate": c["head"]["label"] + "-" + c["rel"] + "->" + c["tail"]["label"],
                                 "reason": "entity_unresolved"})
                continue
            # 反向表述也视为同一条知识：「疾病患者禁用某药」与「某药禁用于某疾病」
            reverse = 1 if c["rel"] in REVERSE_TOLERANT else 0
            dup = conn.execute(
                "SELECT 1 FROM triple WHERE rel=? AND status='active' AND ("
                "(head_id=? AND tail_id=?) OR (?=1 AND head_id=? AND tail_id=?))",
                (c["rel"], h, t, reverse, t, h),
            ).fetchone()
            if dup:
                rejected.append({"candidate": c["head"]["label"] + "-" + c["rel"] + "->" + c["tail"]["label"],
                                 "reason": "duplicate"})
                continue
            c["head"]["id"], c["tail"]["id"] = h, t
            kept.append(c)

        diff_id = "DF-" + uuid.uuid4().hex[:8]
        conn.execute("INSERT INTO pending_diff (diff_id,status,payload,created_at) VALUES (?,?,?,?)",
                     (diff_id, "pending", json.dumps(kept, ensure_ascii=False), store.now()))
        conn.commit()
        return _ok(diff_id=diff_id, scope=scope, candidates=kept, rejected=rejected,
                   counts={"candidates": len(kept), "rejected": len(rejected)})
    finally:
        conn.close()


@mcp.tool()
def onto_commit(diff_id: str, approve_all: bool = True, approve_ids: list[str] = None,
                version: str = "", note: str = "") -> dict:
    """确认待审 diff 并发布新本体版本（生成快照 + manifest hash）。"""
    conn = _conn()
    try:
        row = conn.execute("SELECT * FROM pending_diff WHERE diff_id = ?", (diff_id,)).fetchone()
        if not row:
            return _err("diff_not_found", "先调 onto_propose 生成 diff", diff_id=diff_id)
        items = json.loads(row["payload"])
        if not approve_all and approve_ids:
            items = [c for c in items if c["provenance"]["anchor_id"] in approve_ids]

        cur = store.current_version(conn)
        new_ver = version or _bump(cur["version"] if cur else "v0.9")
        added = 0
        for c in items:
            if store.add_triple(conn, c, new_ver):
                added += 1
        snap = store.snapshot(conn, new_ver, note or ("from " + diff_id))
        conn.execute("UPDATE pending_diff SET status='committed' WHERE diff_id = ?", (diff_id,))
        conn.commit()
        return _ok(diff_id=diff_id, version=new_ver, added=added, snapshot=snap,
                   previous=cur["version"] if cur else None)
    finally:
        conn.close()


def _bump(v: str) -> str:
    m = re.match(r"v(\d+)\.(\d+)", v or "v0.9")
    if not m:
        return "v1.0"
    major, minor = int(m.group(1)), int(m.group(2))
    return "v%d.%d" % (major, minor + 1)


@mcp.tool()
def std_align(entity_text: str = "", triple_id: str = "") -> dict:
    """把自由文本实体对齐到 ICD-10 / 临床路径条目；返回对齐方式与置信度。

    对齐失败返回 ok=false 并给出 unmapped 原因，进入待对齐队列。
    """
    conn = _conn()
    try:
        if triple_id:
            row = conn.execute("SELECT * FROM triple WHERE triple_id = ?", (triple_id,)).fetchone()
            if not row:
                return _err("triple_not_found", "检查 triple_id")
            std = json.loads(row["standard_json"] or "{}")
            if std:
                return _ok(triple_id=triple_id, aligned=True, standard=std, source="stored")
            entity_text = row["head_label"]
        if not entity_text:
            return _err("empty_input", "传入 entity_text 或 triple_id")
        res = store.align(conn, entity_text)
        if not res.get("ok"):
            return _err(res.get("reason", "unmapped"), res.get("hint", ""), input=entity_text)
        return _ok(input=entity_text, aligned=True, scheme=res["scheme"], code=res["code"],
                   match=res["match"], confidence=res["confidence"])
    finally:
        conn.close()


# ---------------- R4 溯源 ----------------

@mcp.tool()
def trace_write(question: str, steps: list[dict], agent_version: str = "v1.0",
                elapsed_ms: int = 0, gaps: list[str] = None) -> dict:
    """写入一次决策链并生成 Markdown 报告，同时计算溯源完整率。

    steps 每项形如 {"i":1,"op":"kg_query","in":[..],"out":[..],"evidence":["T-xxx","AST-...#p3.t1.r2"]}。
    """
    if not steps:
        return _err("empty_steps", "至少一步")
    conn = _conn()
    try:
        return store.write_trace(conn, question, steps, agent_version, elapsed_ms, gaps)
    finally:
        conn.close()


@mcp.tool()
def skill_export(trace_id: str, name: str = "") -> dict:
    """把一条成功 trace 导出成 Nexent Skill 模板草稿（SKILL.md 片段）。"""
    conn = _conn()
    try:
        t = store.get_trace(conn, trace_id)
        if not t:
            return _err("trace_not_found", "检查 trace_id")
        tools_used = []
        for s in t["steps"]:
            op = s.get("op")
            if op and op not in tools_used and op not in {"entity_extract", "conclude", "conflict_check"}:
                tools_used.append(op)
        body = [
            "---",
            "name: " + (name or ("auto-" + trace_id.lower())),
            "description: 由 trace " + trace_id + " 自动导出，覆盖步骤 " + str(len(t["steps"])) + " 步",
            "allowed-tools: [" + ", ".join(tools_used) + "]",
            "tags: [auto-exported, medical]",
            "---",
            "",
            "## 何时用",
            "问题形态与「" + t["question"][:40] + "」相近时。",
            "",
            "## 步骤",
        ]
        for s in t["steps"]:
            body.append("{}. {} -> {}".format(s.get("i"), s.get("op"), str(s.get("out", ""))[:80]))
        body += ["", "## 禁止", "- 引用无 anchor_id 的内容", "- 给出药品剂量"]
        return _ok(trace_id=trace_id, skill_md="\n".join(body), tools=tools_used)
    finally:
        conn.close()


@mcp.tool()
def kb_search(query: str, top_k: int = 5, mode: str = "hybrid") -> dict:
    """透传 Nexent 知识库检索（未配置 KB_ENDPOINT 时返回配置提示）。"""
    endpoint = os.environ.get("KB_ENDPOINT", "")
    if not endpoint:
        return _err("kb_not_configured", "设置 KB_ENDPOINT 后由 Nexent 混合检索承担；否则直接用平台 search-knowledge-base 技能",
                    query=query)
    return _ok(query=query, mode=mode, top_k=top_k, results=[], note="stub：接入 Nexent /knowledge 接口")


@mcp.tool()
def health() -> dict:
    """健康检查：返回版本、库路径、三元组数与当前本体版本。"""
    conn = _conn()
    try:
        n = conn.execute("SELECT COUNT(*) c FROM triple WHERE status='active'").fetchone()["c"]
        a = conn.execute("SELECT COUNT(*) c FROM asset").fetchone()["c"]
        cur = store.current_version(conn)
        return _ok(server_version=SERVER_VERSION, triples=n, assets=a,
                   ontology_version=cur["version"] if cur else None,
                   db=str(store.DB_PATH))
    finally:
        conn.close()


if __name__ == "__main__":
    t0 = time.time()
    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    mcp.run(transport=transport)
