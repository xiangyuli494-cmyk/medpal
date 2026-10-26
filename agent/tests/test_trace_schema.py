"""trace.json v1 schema 的校验测试 —— 卡住「schema 写了但没生效」这个最坑的失败模式。

为什么这份测试比文档本身更重要：文档是提示，测试是执法。store.write_trace 有三处
静默容错（evidence 传字符串会被逐字符遍历、缺 i/in/out 不报错只渲染空表格、
步序不排序），这三处都不会抛异常，只会产出看起来正常但实际是垃圾的报告。
没有测试，它们会一直躺在库里，直到答辩前 T3 画图才发现对不上。

跑：python -m pytest tests/test_trace_schema.py -q
"""

from __future__ import annotations

import json
import shutil
import sqlite3
import sys
from pathlib import Path

import pytest

AGENT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AGENT / "mcp-server"))
sys.path.insert(0, str(AGENT / "tools"))

import store  # noqa: E402
import validate_trace as V  # noqa: E402

FIXTURE = AGENT / "tests" / "fixtures" / "trace_v1_example.json"
SAMPLE_DB = AGENT / "mcp-server" / "data" / "medpal.db"


@pytest.fixture()
def db(tmp_path):
    """永远在副本上跑，绝不碰 agent/mcp-server/data/medpal.db。"""
    if not SAMPLE_DB.exists():
        pytest.skip("缺 seed 库，先跑 python mcp-server/seed.py")
    dst = tmp_path / "t.db"
    shutil.copy(SAMPLE_DB, dst)
    conn = sqlite3.connect(str(dst))
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


def test_fixture_is_valid():
    t = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert V.validate(t) == []
    assert t["schema"] == "medpal-trace/1"
    assert t["sources"] == ["AST-2026-000137"]


def test_fixture_matches_disk_schema_file():
    """文档、JSON Schema 文件、fixture 三者不许漂移。"""
    t = json.loads(FIXTURE.read_text(encoding="utf-8"))
    schema = V.load_schema()
    assert schema["properties"]["schema"]["const"] == t["schema"]
    assert set(schema["required"]) <= set(t)


@pytest.mark.parametrize(
    "mutate,expect",
    [
        (lambda t: t.pop("trace_id"), "trace_id"),
        (lambda t: t.__setitem__("schema", "walking-skeleton/1"), "medpal-trace/1"),
        (lambda t: t["steps"][0].__setitem__("evidence", "T-d2e6d769"), "逐字符"),
        (lambda t: t["steps"][0].__setitem__("evidence", ["不是证据"]), "格式非法"),
        (lambda t: t["steps"].reverse(), "严格递增"),
        (lambda t: t["steps"][0].__setitem__("i", 9), "严格递增"),
        (lambda t: t["steps"][2].__setitem__("ref", "PARSE"), "应为 ref"),
        (lambda t: t.__setitem__("trace_completeness", 1.5), "maximum of 1"),
        (lambda t: t.__setitem__("trace_id", "TR-2026-05BE"), "does not match"),
    ],
)
def test_known_bad_traces_are_rejected(mutate, expect):
    t = json.loads(FIXTURE.read_text(encoding="utf-8"))
    mutate(t)
    errs = V.validate(t)
    assert errs, "这个改动本该被拒绝，但校验器放过了"
    assert any(expect in e for e in errs), "错误信息里没提到 %r，实际：%r" % (expect, errs)


def test_evidence_string_is_the_silent_killer(db):
    """实测证据：evidence 传字符串，store 会逐字符当证据，溯源完整率直接掉到 0。

    这不是假想。原样复刻 store.py:526-534 的行为：
        write_trace(..., evidence="T-d2e6d769")
        -> evidence_count=8, unresolved=['T','-','d','2',...]
    所以 schema 把 evidence 定死成 array，并且校验器额外再验元素格式。
    """
    r = store.write_trace(
        db,
        "测试：evidence 传字符串",
        [{"i": 1, "op": "kg_query", "evidence": "T-d2e6d769"}],
        "t",
        0,
        [],
    )
    assert r["evidence_count"] == 8
    assert r["trace_completeness"] == 0.0
    t = V.load_from_db(Path(db.execute("PRAGMA database_list").fetchone()[2]), 1)[0]
    assert any("逐字符" in e for e in V.validate(t))


def test_missing_i_renders_none_but_schema_catches_it(db):
    r = store.write_trace(db, "测试：缺 i", [{"op": "kg_query", "evidence": []}], "t", 0, [])
    assert r["ok"] is True  # store 完全不报错
    t = V.load_from_db(Path(db.execute("PRAGMA database_list").fetchone()[2]), 1)[0]
    errs = V.validate(t)
    assert any("'i' is a required property" in e for e in errs)


def test_completeness_formula_matches_store():
    """校验器的重算口径必须和 store.write_trace 一致，否则「库里 1.0、校验器 0.9」。"""
    t = json.loads(FIXTURE.read_text(encoding="utf-8"))
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE triple (triple_id TEXT)")
    conn.execute("CREATE TABLE asset (asset_id TEXT, anchors_json TEXT)")
    conn.execute("INSERT INTO triple VALUES ('T-d331cf32')")
    conn.execute("INSERT INTO triple VALUES ('T-b5d99245')")
    conn.execute(
        "INSERT INTO asset VALUES ('AST-2026-000137', ?)",
        (
            json.dumps(
                [
                    {"anchor_id": "AST-2026-000137#" + x}
                    for x in ["s2.p1.c3", "s3.p1.c1", "s1.h", "s2.p1.c2", "s3.p1.c2"]
                ]
            ),
        ),
    )
    cited, unresolved = V._recount(conn, t["steps"])
    assert unresolved == []
    assert round(1 - len(unresolved) / len(cited), 3) == t["trace_completeness"]
    conn.close()


def test_skeleton_dialect_is_rejected_then_migrates():
    """骨架期方言必须被拒（否则两套 schema 混用），且能一键迁到 v1。"""
    p = AGENT.parent / "tmp" / "trace.json"
    if not p.exists():
        pytest.skip("缺 tmp/trace.json，先跑 python -m agent.skeleton")
    raw = json.loads(p.read_text(encoding="utf-8"))
    assert raw["schema"] == "walking-skeleton/1"
    assert V.validate(raw), "旧方言不该通过 v1 校验"
    migrated = V.migrate(raw)
    assert V.validate(migrated) == []
    assert migrated["schema"] == "medpal-trace/1"
    assert [s["i"] for s in migrated["steps"]] == [1, 2, 3, 4, 5]
    assert migrated["steps"][3]["op"] == "kg_query"  # reason_2hop -> kg_query
    assert migrated["sources"] == ["AST-2026-000137"]
    assert any("已改挂" in g for g in migrated["gaps"])  # 迁移留痕，不静默


def test_ref_must_agree_with_op():
    """ref 与 op 同说一件事，写了就必须对得上（docs §3.2）。

    这条以前是空话：REF_BY_OP 在 validate_trace.py 里定义着却没人用，
    所以 op=kg_query 而 ref=PARSE 这种自相矛盾的记录能一路过关。
    """
    t = json.loads(FIXTURE.read_text(encoding="utf-8"))
    for s in t["steps"]:
        s.pop("ref", None)
    assert V.validate(t) == []  # 省掉 ref 是合法的

    t["steps"][2]["ref"] = "TRAVERSE"
    assert V.validate(t) == []  # 写对了也合法

    t["steps"][2]["ref"] = "PARSE"
    errs = V.validate(t)
    assert any("'TRAVERSE'" in e and "'PARSE'" in e for e in errs), errs


def test_derive_sources_needs_conn_for_triples():
    """T- 开头的证据要靠 triple.asset_id 反推；不连库宁可缺，不能猜。"""
    t = {"steps": [{"evidence": ["T-d331cf32", "AST-2026-000137#s1.h"]}]}
    assert V.derive_sources(t) == ["AST-2026-000137"]
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE triple (triple_id TEXT, asset_id TEXT)")
    conn.execute("INSERT INTO triple VALUES ('T-d331cf32', 'AST-2026-000155')")
    assert V.derive_sources(t, conn) == ["AST-2026-000137", "AST-2026-000155"]
    conn.close()


def test_db_mode_runs_and_reports():
    """CI 门禁用 --quiet --db 这条路径，必须能跑、能返回 0/1。"""
    if not SAMPLE_DB.exists():
        pytest.skip("缺 seed 库")
    code = V.main(["--db", str(SAMPLE_DB), "--limit", "3", "--quiet"])
    assert code in (0, 1)
