import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path("agent")
SAMPLES = ROOT / "data" / "samples"
CARDS = ROOT / "data" / "asset-cards"
DB = ROOT / "mcp-server" / "data" / "medpal.db"
sys.path.insert(0, str((ROOT / "mcp-server").resolve()))
import server  # noqa: E402


def business_title(path: Path) -> str:
    """给台账一个像样的标题：md 取一级标题，其余按类型给中文名并带序号。"""
    if path.suffix.lower() == ".md":
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("# "):
                return line[2:].strip()[:60]
    stem = path.stem
    num = "".join(ch for ch in stem if ch.isdigit())
    label = {"bingli": "合成门诊病历", "menzhen": "门诊记录",
             "pathway": "临床路径摘要", "reference": "检验参考区间"}.get(
        stem.split("_")[0], stem)
    return f"{label} {num}".strip() if num else label


def main() -> int:
    samples = sorted(p for p in SAMPLES.rglob("*") if p.is_file())
    # 幂等：清空台账再入库，避免重复 ingest 翻倍
    con = sqlite3.connect(str(DB))
    con.execute("delete from asset")
    con.commit()
    con.close()

    mapping = {}
    for path in samples:
        res = server.ingest_asset(path=str(path), source_type="synthetic",
                                  ingested_by="T5", title=business_title(path))
        if res.get("asset_id"):
            mapping[path.name] = res.get("modality") or "?"

    con = sqlite3.connect(str(DB))
    con.row_factory = sqlite3.Row
    rows = con.execute("select * from asset order by created_at desc").fetchall()
    con.close()

    for old in CARDS.glob("*.json"):
        old.unlink()
    for r in rows:
        card = {
            "asset_id": r["asset_id"], "title": r["title"], "modality": r["modality"],
            "source": json.loads(r["source_json"] or "{}"),
            "version": json.loads(r["version_json"] or "{}"),
            "sensitivity": r["sensitivity"],
            "structure": json.loads(r["structure_json"] or "{}"),
            "anchors": json.loads(r["anchors_json"] or "[]"),
            "entities": json.loads(r["entities_json"] or "[]"),
            "kb": {"base": "med-text", "doc_id": "", "status": r["kb_status"] or "ready"},
            "ingested_by": r["ingested_by"], "created_at": r["created_at"],
        }
        (CARDS / f"{card['asset_id']}.json").write_text(
            json.dumps(card, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"样本 {len(samples)} 份 | 入库 {len(rows)} 行 | 导出 {len(rows)} 张卡")
    per_dir = {}
    for path in samples:
        per_dir[path.parent.name] = per_dir.get(path.parent.name, 0) + 1
    print("  按目录:", per_dir)
    per_mod = {}
    for name, m in mapping.items():
        per_mod[m] = per_mod.get(m, 0) + 1
    print("  按模态:", per_mod)
    odd = [(n, m) for n, m in mapping.items() if (n.endswith((".csv", ".xlsx")) and m != "table")]
    if odd:
        print("  ⚠ 表格类但模态不是 table:", odd)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
