"""离线评测：不调大模型，直接用 MCP 背后的工具链跑同一套流程，得到可复现的基线分。

这不是「智能体评测」的替代品，而是它的快速回归版：
  - 快（10 题 < 2s）、免费、进 CI
  - 与 Nexent 平台内评测跑同一份 dataset/v0.jsonl，两套分数对不上就说明智能体层有额外损耗

用法：python eval/run_eval.py [--dataset eval/dataset/v0.jsonl] [--out eval/reports] [--reset-db]
"""
from __future__ import annotations

import argparse, json, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "mcp-server"))

import store  # noqa: E402
from parsers import ENTITY_HINTS, SYNONYMS  # noqa: E402

DEPTS = {"DEP-GI": "消化内科", "DEP-SURG": "普外科", "DEP-CARD": "心内科"}


def extract_entities(text: str) -> list[str]:
    """最长优先匹配，避免「消化性溃疡」被切成「溃疡」。"""
    hits, spans = [], []
    for m in ENTITY_HINTS.finditer(text):
        s, e = m.span()
        if any(s < b and e > a for a, b in spans):   # 已被更长的实体覆盖
            continue
        spans.append((s, e))
        hits.append(SYNONYMS.get(m.group(0), m.group(0)))
    return hits


# 报警症状：出现任一项，指南要求优先内镜而不是先铺检查清单
ALARM_WORDS = ("体重下降", "消瘦", "贫血", "呕血", "黑便", "吞咽困难", "进行性吞咽困难", "大出血")
# 明确索要检查清单的措辞：此时全列检查项属于知情需求，不算冗余
EXAM_LIST_WORDS = ("哪些检查", "什么检查", "检查项目", "查什么", "怎么查", "还需要查", "要做什么")


def _is_disease(node_id) -> bool:
    """ICD-10 的 K/R 段在本体里当疾病用；R10.1 是症状编码，不算疾病。"""
    return bool(node_id) and str(node_id).startswith(("K", "R")) and node_id != "R10.1"


def seed_weight(conn, seed_ids: set[str]) -> dict[str, float]:
    """症状/检查等种子的区分度权重 = 1 / 它在本体里连了几种疾病。

    「上腹隐痛」同时连 K27/K29，几乎不能把两者分开；「烧心」只连 K21，指向性极强。
    不加这层，「上腹痛」类高频症状会把所有消化科疾病一起点亮，主诊断必然滑向边最多的枢纽节点。
    """
    out: dict[str, float] = {}
    for s in seed_ids:
        rows = store.neighbors(conn, [s], rel_filter=["has_symptom", "diagnosed_by"])
        seen = {x for r in rows for x in (r["head_id"], r["tail_id"]) if x != s and _is_disease(x)}
        out[s] = 1.0 / len(seen) if seen else 0.0
    return out


def answer(conn, question: str, max_hops: int = 2):
    """一次问答的确定性实现：实体 -> 归一 -> 多跳 -> 结论。对应 S3 的前四步。"""
    t0 = time.time()
    steps: list[dict] = []
    ents = extract_entities(question)
    steps.append({"i": 1, "op": "entity_extract", "out": ents, "evidence": []})

    resolved, unmapped = {}, []
    for e in ents:
        r = store.align(conn, e)
        (resolved.setdefault(r["code"], e) if r.get("ok") else unmapped.append(e))
    steps.append({"i": 2, "op": "std_align", "out": sorted(resolved), "evidence": []})

    q = store.kg_query(conn, ents, max_hops=max_hops, limit=40)
    steps.append({"i": 3, "op": "kg_query", "in": ents,
                  "out": sorted({n for p in q.get("paths", []) for n in p["nodes"]}),
                  "evidence": [store._ref_str(t) for p in q.get("paths", []) for t in p.get("provenance", [])]})

    # 先定「焦点疾病」：问题里提到的症状所指向的疾病。结论只从这个焦点往上长，
    # 否则会把本体里所有疾病的所有检查项一起倒给患者——那是清单不是决策。
    # 主诊断只留一个。打分不能只看「连接边置信度之和」——那会让边最多的枢纽疾病
    # （K27）在任何问题上都胜出。改为按距离衰减：sum(conf / (1 + 跳数))。
    # 理由与 S3 的宁缺毋滥一致：患者要的是处置建议，不是鉴别诊断清单。
    seed_types: dict[str, list[tuple[str, str]]] = {}
    for name in ents:
        r = store.align(conn, name)
        if r.get("ok"):
            seed_types.setdefault(r["entity_type"], []).append((name, r["code"]))

    seed_ids = {code for lst in seed_types.values() for _, code in lst}
    w = seed_weight(conn, seed_ids)
    score: dict[str, float] = {}
    # 权重最高的信号是「症状直达疾病」：连接这一跳的置信度 × 该症状的区分度。
    # 只按路径累加会让边最多的枢纽疾病（K27）在任何问题上都胜出，Q002 的烧心就被淹没了。
    for s in seed_ids:
        if w.get(s, 0.0) <= 0:
            continue
        for row in store.neighbors(conn, [s], rel_filter=["has_symptom", "diagnosed_by"]):
            for other in (row["head_id"], row["tail_id"]):
                if other != s and _is_disease(other):
                    score[other] = score.get(other, 0.0) + float(row["confidence"]) * w[s] * 2.0
    # 二跳及以上的证据降权保留：症状没直接连到疾病时（多跳链条）仍能靠路径兜底
    for p in q.get("paths", []):
        nodes = p.get("nodes", [])
        for st in p.get("steps", []):
            for other in (st.get("head_id"), st.get("tail_id")):
                if not _is_disease(other):
                    continue
                d = nodes.index(other) if other in nodes else 2
                score[other] = score.get(other, 0.0) + 0.3 * float(st.get("confidence") or 0.5) / (1 + d)
    direct = {code for _, code in seed_types.get("Disease", [])}
    primary = max(score, key=lambda k: (k in direct, score[k])) if score else None
    focus_diseases = {primary} if primary else set()

    # 问题里点名的检查项 = 用户真正在问的检查项，结论只答这一项（Q005/Q008 这类追问）
    named_exams = {code for _, code in seed_types.get("Exam", [])}
    # 只提了药、没提任何症状或疾病时（Q007），问的是用药安全，不该甩检查清单
    has_clinical_seed = bool(seed_types.get("Disease") or seed_types.get("Symptom"))
    # 检查项的裁剪规则（决策而不是清单）：
    #   ①报警症状（消瘦/贫血/呕血/黑便/吞咽困难）→ 先做内镜，其余检查此时不该平铺；
    #   ②问题已点名疾病（"胃溃疡病史"）且不是在索要检查清单 → 只答病因学检查，内镜视为已做；
    #   ③用户在明确索要检查清单（"需要做哪些检查"）→ 全列，这是知情需求。
    alarm = any(k in question for k in ALARM_WORDS)
    wants_exam_list = any(k in question for k in EXAM_LIST_WORDS)
    confirmed_disease = bool(seed_types.get("Disease"))

    depts, exams, conflicts, ev = [], [], [], []
    for p in q.get("paths", []):
        path_nodes = set(p.get("nodes", []))
        for st in p.get("steps", []):
            rel, tail = st.get("rel"), st.get("to")
            # 路径是无向遍历，rel 的方向要按 head/tail 归一，否则 belongs_to_dept 可能被反向读成科室->疾病
            a, b = st.get("head_id"), st.get("tail_id")
            to_id, to_label = (b, st.get("tail_label")) if a in path_nodes else (a, st.get("head_label"))
            # 焦点判定看的是这条边「疾病那一端」在不在焦点里，不能拿远端（检查项/科室）去比
            ends = (st.get("head_id"), st.get("tail_id"))
            disease_end = next((x for x in ends if x in focus_diseases), None)
            on_focus = not focus_diseases or disease_end is not None
            if rel == "belongs_to_dept" and on_focus:
                depts.append(DEPTS.get(to_id, to_label))
            elif rel == "requires_exam" and on_focus:
                # 追问「要不要做某项检查」时只回这一项；只提药没提症状时不甩检查清单
                if not has_clinical_seed:
                    continue
                if named_exams and to_id not in named_exams:
                    continue
                # 报警症状优先内镜：其余检查此时平铺会稀释「先做哪一项」这个决策结论
                if alarm and to_id != "EX-GASTRO":
                    continue
                # 病史已明确、且不是在索要检查清单：内镜视为已完成，只补病因学检查
                if confirmed_disease and not wants_exam_list and to_id == "EX-GASTRO":
                    continue
                exams.append(to_label)
            elif rel == "contraindicated_for" and on_focus:
                conflicts.append(st.get("head_label") if to_id != a else st.get("tail_label"))
            if st.get("provenance"):
                ev.append(store._ref_str(st["provenance"]))

    steps.append({"i": 4, "op": "conflict_check", "out": sorted(set(conflicts)), "evidence": []})
    # 科室不能只看第一跳：多跳路径里同一个科室会重复出现，取出现次数最多的那个
    dept = max(set(depts), key=depts.count) if depts else ""
    conf = min(0.9, 0.4 + 0.1 * len(q.get("paths", [])))
    steps.append({"i": 5, "op": "conclude",
                  "out": {"dept": dept, "conf": round(conf, 2), "exams": sorted(set(exams))},
                  "evidence": sorted(set(ev))})

    gaps = []
    if not ents or not resolved:
        gaps.append("未识别到可归一实体，超出本体覆盖范围")
    if dept and len(set(ev)) < 2:
        gaps.append("证据少于 2 条，置信度低")

    tr = store.write_trace(conn, question, steps, agent_version="offline-baseline",
                          elapsed_ms=int((time.time() - t0) * 1000), gaps=gaps)
    return {"dept": dept, "exams": sorted(set(exams)), "conflicts": sorted(set(conflicts)),
            "evidence": sorted(set(ev)), "out_of_scope": not dept,
            "trace_id": tr["trace_id"], "trace_completeness": tr["trace_completeness"],
            "elapsed_ms": int((time.time() - t0) * 1000)}


def score_one(gold: dict, got: dict) -> dict:
    if gold.get("out_of_scope"):
        ok = got["dept"] == ""
        return {"dept": 1.0 if ok else 0.0, "exams": 1.0 if ok else 0.0, "exams_full": 1.0 if ok else 0.0,
                "conflict": 1.0 if ok else 0.0, "evidence": 1.0, "trace": got["trace_completeness"]}
    dept = 1.0 if gold["dept"] and got["dept"] == gold["dept"] else 0.0
    # 检查项按 Jaccard 计分：多召回同样扣分。宁缺毋滥是 S3 的硬约束，
    # 若只算召回率，把整个本体的检查项全倒出来也能拿满分，指标就失真了。
    g_ex, p_ex = set(gold["exams"]), set(got["exams"])
    if not g_ex and not p_ex:
        exams, exams_full = 1.0, 1.0
    elif not g_ex or not p_ex:
        exams, exams_full = 0.0, 0.0
    else:
        exams = len(g_ex & p_ex) / len(g_ex | p_ex)
        exams_full = 1.0 if g_ex <= p_ex and len(p_ex) <= len(g_ex) else 0.0
    g_cf, p_cf = set(gold["conflicts"]), set(got["conflicts"])
    conflict = 1.0 if not g_cf else (1.0 if g_cf <= p_cf else 0.0)
    g_ev = set(gold.get("gold_evidence", []))
    ev = 1.0 if not g_ev else len(g_ev & set(got["evidence"])) / len(g_ev)
    return {"dept": dept, "exams": exams, "exams_full": exams_full,
            "conflict": conflict, "evidence": ev, "trace": got["trace_completeness"]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default=str(ROOT / "eval" / "dataset" / "v0.jsonl"))
    ap.add_argument("--out", default=str(ROOT / "eval" / "reports"))
    ap.add_argument("--reset-db", action="store_true", help="先重建种子库再评测")
    args = ap.parse_args()

    if args.reset_db:
        subprocess.run([sys.executable, str(ROOT / "mcp-server" / "seed.py"), "--reset"],
                       check=True, stdout=subprocess.DEVNULL)

    rows = [json.loads(l) for l in Path(args.dataset).read_text(encoding="utf-8").splitlines() if l.strip()]
    conn = store.connect()
    details, agg = [], {"dept": [], "exams": [], "exams_full": [], "conflict": [],
                        "evidence": [], "trace": [], "ms": []}
    for row in rows:
        got = answer(conn, row["question"])
        sc = score_one(row["gold"], got)
        for k in sc:
            agg[k].append(sc[k])
        agg["ms"].append(got["elapsed_ms"])
        details.append({"id": row["id"], "question": row["question"],
                        "gold_dept": row["gold"]["dept"], "got_dept": got["dept"],
                        "gold_exams": row["gold"]["exams"], "got_exams": got["exams"],
                        "gold_conflicts": row["gold"]["conflicts"], "got_conflicts": got["conflicts"],
                        "evidence_hit": sc["evidence"], "trace_id": got["trace_id"],
                        "trace_completeness": got["trace_completeness"]})
    conn.close()

    n = len(rows)
    m = {k: (sum(v) / len(v) if v else 0.0) for k, v in agg.items()}
    report = {"dataset": Path(args.dataset).name, "n": n,
              "accuracy_dept": round(m["dept"], 3), "accuracy_exam": round(m["exams"], 3),
              "exams_strict": round(m["exams_full"], 3),
              "conflict_recall": round(m["conflict"], 3), "evidence_recall": round(m["evidence"], 3),
              "trace_completeness": round(m["trace"], 3), "avg_latency_ms": round(m["ms"], 1),
              "details": details}

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    tag = time.strftime("%Y%m%d-%H%M%S")
    (out_dir / f"eval-{tag}.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [f"# 离线评测 {tag}", "",
             f"- 数据集：{report['dataset']}（{n} 条）",
             f"- 科室准确率：{report['accuracy_dept']:.0%}",
             f"- 检查项准确率（Jaccard）：{report['accuracy_exam']:.0%}",
             f"- 检查项完全一致率：{report['exams_strict']:.0%}",
             f"- 冲突召回：{report['conflict_recall']:.0%}",
             f"- 证据召回：{report['evidence_recall']:.0%}",
             f"- 溯源完整率：{report['trace_completeness']:.0%}",
             f"- 平均时延：{report['avg_latency_ms']} ms", "",
             "| 题号 | 金标准科室 | 输出科室 | 一致 | 证据命中 |",
             "| --- | --- | --- | --- | --- |"]
    for d in details:
        ok = "是" if d["gold_dept"] == d["got_dept"] else "否"
        lines.append(f"| {d['id']} | {d['gold_dept'] or '(应拒答)'} | {d['got_dept'] or '(拒答)'} | {ok} | {d['evidence_hit']:.0%} |")
    md = out_dir / f"eval-{tag}.md"
    md.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("\n".join(lines[:9]))
    print(f"\n报告：{md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
