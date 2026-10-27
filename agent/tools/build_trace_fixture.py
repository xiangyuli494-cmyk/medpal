"""重新生成 tests/fixtures/trace_v1_example.json。

为什么需要这个脚本：fixture 如果不是可复现的，半年后没人知道那份 JSON 是手抄的还是真跑出来的。
这个脚本走真实写入路径 —— 拷一份 seed 库到临时目录，调 store.write_trace 真写一条，
再用 tools/validate_trace.py 的同一套逻辑读回来落盘。全程不碰 agent/mcp-server/data/medpal.db。

    python tools/build_trace_fixture.py

产出：tests/fixtures/trace_v1_example.json
"""

from __future__ import annotations

import json
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

AGENT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(AGENT / "mcp-server"))
sys.path.insert(0, str(AGENT / "tools"))

import store  # noqa: E402
import validate_trace as V  # noqa: E402

SEED = AGENT / "mcp-server" / "data" / "medpal.db"
OUT = AGENT / "tests" / "fixtures" / "trace_v1_example.json"

QUESTION = "反复上腹隐痛3个月，夜间加重，进食后缓解，近两周服用布洛芬"

# 一条合规的离线基线 trace：五步、证据全带 anchor、一条步骤带 confidence。
STEPS = [
    {"i": 1, "op": "entity_extract", "out": ["上腹隐痛", "布洛芬"], "evidence": []},
    {"i": 2, "op": "std_align", "out": ["DRUG-IBU", "SYM-EPI"], "evidence": []},
    {
        "i": 3,
        "op": "kg_query",
        "in": ["上腹隐痛", "布洛芬"],
        "out": ["K27", "ICD10-K27", "EX-HP-BT", "DEP-GI"],
        "evidence": [
            "T-d331cf32",
            "T-b5d99245",
            "AST-2026-000137#s2.p1.c3",
            "AST-2026-000137#s3.p1.c1",
        ],
        "confidence": 0.89,
    },
    {"i": 4, "op": "conflict_check", "in": ["布洛芬", "K27"], "out": ["布洛芬"], "evidence": []},
    {
        "i": 5,
        "op": "conclude",
        "out": {"dept": "消化内科", "conf": 0.9, "exams": ["幽门螺杆菌呼气试验", "胃镜检查"]},
        "evidence": [
            "AST-2026-000137#s1.h",
            "AST-2026-000137#s2.p1.c2",
            "AST-2026-000137#s3.p1.c2",
        ],
        "ref": "CONCLUDE",
    },
]


def main() -> int:
    if not SEED.exists():
        print("缺 seed 库，先跑 python mcp-server/seed.py", file=sys.stderr)
        return 2
    tmpdir = Path(tempfile.mkdtemp(prefix="medpal-fixture-"))
    work = tmpdir / "fixture.db"
    shutil.copy(SEED, work)
    conn = sqlite3.connect(str(work))
    conn.row_factory = sqlite3.Row
    r = store.write_trace(conn, QUESTION, STEPS, "offline-baseline", 13, [])
    conn.close()
    if not r.get("ok"):
        print("写入失败：%r" % (r,), file=sys.stderr)
        return 2

    trace = V.load_from_db(work, 1)[0]
    errs = V.validate(trace)
    shutil.rmtree(tmpdir, ignore_errors=True)
    if errs:
        print("生成的 fixture 自身不合规，不落盘：", file=sys.stderr)
        for e in errs:
            print("  - " + e, file=sys.stderr)
        return 1

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(trace, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        "wrote %s (%s, %d steps, completeness=%s)"
        % (OUT, trace["trace_id"], len(trace["steps"]), trace["trace_completeness"])
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
