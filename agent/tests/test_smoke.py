"""离线冒烟测试：不依赖 Nexent、不联网，直接调用 MCP 工具函数。

覆盖赛题四条要求的可验证最小闭环：
  R1 ingest_asset / get_asset_card
  R2 kg_query / std_align / onto_propose / onto_commit
  R4 trace_write / skill_export
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "mcp-server"
sys.path.insert(0, str(ROOT))

TMP = Path(__file__).resolve().parents[1] / "tmp"
TMP.mkdir(exist_ok=True)
os.environ["MEDPAL_DB"] = str(TMP / "smoke.db")
if (TMP / "smoke.db").exists():
    (TMP / "smoke.db").unlink()

import store  # noqa: E402

store.DATA_DIR = TMP
store.DB_PATH = TMP / "smoke.db"
store.REPORT_DIR = TMP / "reports"

import seed  # noqa: E402
import server  # noqa: E402

seed.main(reset=True)
fails = []


def check(name, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + name + ("  " + str(detail) if detail and not cond else ""))
    if not cond:
        fails.append(name)


print("[R1] 多模态资产识别与标识")
doc = TMP / "pathway_k27.md"
doc.write_text(seed.SAMPLE_PATH.read_text(encoding="utf-8"), encoding="utf-8")
r = server.ingest_asset(str(doc), title="消化性溃疡临床路径（2023 版）", ingested_by="T2")
check("ingest_asset 成功", r["ok"], r)
asset_id = r["asset_id"]
check("生成资产 id", asset_id.startswith("AST-"), asset_id)
check("产出可引用锚点", len(r["anchors"]) >= 3, len(r["anchors"]))
check("锚点 id 与资产绑定", all(a["anchor_id"].startswith(asset_id) for a in r["anchors"]))
check("自动识别实体（最长匹配）", "消化性溃疡" in r["entity_hint"], r["entity_hint"])

r = server.get_asset_card(asset_id=asset_id)
check("按 id 取卡片", r["ok"] and r["cards"][0]["title"], r)
r = server.get_asset_card(modality="text")
check("按模态筛选", r["ok"] and r["count"] >= 1, r.get("count"))

print("[R2] 本体多跳与标准对齐")
r = server.kg_query(["上腹隐痛"], max_hops=2)
check("多跳查询有路径", r["ok"] and len(r["paths"]) > 0, r.get("reason"))
check("路径带 provenance", any(p["provenance"] for p in r["paths"]))
check("命中消化性溃疡", any("K27" in p["nodes"] for p in r["paths"]))
r = server.kg_query(["幽门螺杆菌"], max_hops=1, rel_filter=["requires_exam"])
check("关系过滤生效", all("requires_exam" in [s["edge"].split("-[")[1].split("]")[0] for s in p["steps"]] for p in r["paths"]))
r = server.kg_query([])
check("空种子显式报错", r["ok"] is False and r["reason"] == "no_seed")

r = server.std_align(entity_text="胃溃疡")
check("别名对齐到 ICD-10", r["ok"] and r["code"] == "K27", r)
r = server.std_align(entity_text="完全无关的字符串XYZ")
check("未对齐返回 unmapped", r["ok"] is False and r["reason"] == "unmapped", r)

print("[R2] 本体进化：抽取 -> 校验 -> 确认 -> 版本")
# 第一份资产讲的都是本体现有知识，正确行为是被判为 duplicate（不重复入库）
r = server.onto_propose([asset_id])
check("重复知识被拦下", r["ok"] and r["counts"]["candidates"] == 0, r.get("counts"))
check("被拒条目带原因", all("reason" in x for x in r["rejected"]), r["rejected"][:2])
check("本体现有的知识不产生候选（全是 duplicate/no_pattern）",
      all(x["reason"] in ("duplicate", "no_pattern_match", "too_short") for x in r["rejected"]),
      [x["reason"] for x in r["rejected"]])

# 第二份资产带来新知识 -> 应产出候选并推动版本前进
# 刻意写成「种子里没有的新知识 + 一个本体现无的实体」两份内容：
# 前者验证候选三元组能产出，后者验证未解析实体被挡在待建节点队列而不是硬塞进图。
addendum = TMP / "addendum_k29.md"
addendum.write_text(
    "# 慢性胃炎诊疗补充说明\n\n## 用药\n胃炎禁用布洛芬等 NSAIDs 药物。\n"
    "\n## 检查\n胃炎需要做胃蛋白酶原检测以评估萎缩程度。\n",
    encoding="utf-8",
)
r2 = server.ingest_asset(str(addendum), title="慢性胃炎诊疗补充说明", ingested_by="T2")
check("第二份资产入库", r2["ok"], r2)
r = server.onto_propose([r2["asset_id"]])
check("新知识产出候选三元组", r["ok"] and r["counts"]["candidates"] >= 1, r.get("counts"))
check("未解析实体进待建节点队列（胃蛋白酶原不在本体里）",
      any(x.get("reason") == "entity_unresolved" for x in r["rejected"]),
      [x.get("reason") for x in r["rejected"]])
cand = r["candidates"][0] if r["candidates"] else {}
check("候选带 provenance 锚点", bool(cand.get("provenance", {}).get("anchor_id")), cand)
diff_id = r["diff_id"]
r = server.onto_commit(diff_id=diff_id, version="v1.0", note="smoke")
check("发布新版本", r["ok"] and r["version"] == "v1.0", r)
check("版本号自增", r["previous"] == "v0.9", r.get("previous"))
conn = store.connect()
cur = store.current_version(conn)
check("当前指针指向 v1.0", cur and cur["version"] == "v1.0", cur and cur["version"])
d = store.diff_versions(conn, "v0.9", "v1.0")
check("差分可算", "counts" in d, d.get("counts"))
conn.close()

print("[R4] 决策链与溯源")
conn = store.connect()
triple_ok = conn.execute("SELECT triple_id FROM triple WHERE head_id='K27' LIMIT 1").fetchone()[0]
conn.close()
steps = [
    {"i": 1, "op": "entity_extract", "out": ["上腹隐痛", "布洛芬"], "evidence": []},
    {"i": 2, "op": "kg_query", "in": ["上腹隐痛"], "out": ["K27"],
     "evidence": [triple_ok]},
    {"i": 3, "op": "conclude", "out": {"dept": "消化内科", "conf": 0.74},
     "evidence": [asset_id + "#p1.s1"]},
]
r = server.trace_write("反复上腹隐痛3个月，夜间加重，进食后缓解，近两周服用布洛芬", steps)
check("写入 trace", r["ok"] and r["trace_id"].startswith("TR-"), r)
check("生成报告文件", Path(r["report_path"]).exists())
check("溯源完整率可算", 0 <= r["trace_completeness"] <= 1, r["trace_completeness"])
check("不存在的证据被标出", len(r["unresolved"]) == 1, r["unresolved"])
r = server.skill_export(r["trace_id"], name="k27-demo")
check("导出技能模板", r["ok"] and "allowed-tools" in r["skill_md"], r.get("tools"))

print("[平台] 健康检查")
r = server.health()
check("health 可用", r["ok"] and r["triples"] > 0, r)

print()
if fails:
    print("FAILED:", fails)
    sys.exit(1)
print("ALL PASS")
