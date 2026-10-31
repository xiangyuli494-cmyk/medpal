"""批量生成 R1 合成样本与 Asset Card（赛题3 W1 里程碑用）。

全部为 synthetic 数据，不含任何真实患者信息；每份样本配一张卡片。
用法： python agent/tools/gen_samples.py
"""

from __future__ import annotations

import json
import random
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
S = ROOT / "data" / "samples"
CARDS = ROOT / "data" / "asset-cards"

DISEASES = [
    ("K27", "消化性溃疡", "消化内科", ["胃镜", "幽门螺杆菌检测", "血常规"]),
    ("I10", "高血压病", "心血管内科", ["血压监测", "心电图", "肾功能"]),
    ("E11", "2型糖尿病", "内分泌科", ["空腹血糖", "糖化血红蛋白", "眼底检查"]),
    ("J18", "肺炎", "呼吸内科", ["胸片", "血常规", "C反应蛋白"]),
    ("N20", "肾结石", "泌尿外科", ["泌尿系超声", "尿常规", "肾功能"]),
]


def _aid(n: int) -> str:
    return f"AST-2026-{n:06x}"


def _card(asset_id, title, modality, anchors, structure) -> dict:
    return {
        "asset_id": asset_id,
        "title": title,
        "modality": modality,
        "source": {"type": "synthetic", "publisher": "本项目生成", "url": ""},
        "version": {"value": "v1", "captured_at": date.today().isoformat(), "supersedes": None},
        "sensitivity": "public",
        "structure": structure,
        "anchors": anchors,
        "entities": [],
        "kb": {"base": "med-text", "doc_id": "", "status": "pending"},
        "ingested_by": "T5",
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }


def gen_text() -> int:
    made = 0
    for i in range(1, 21):
        code, name, dept, checks = DISEASES[i % len(DISEASES)]
        aid = _aid(2000 + i)
        body = [
            f"# {name}临床路径摘要（合成样例 {i}）",
            "",
            "## 诊断依据",
            f"主诉与检查支持 {name}（ICD-10 {code}），就诊科室 {dept}。",
            "## 检查项目",
            "、".join(checks) + "。",
            "## 治疗原则",
            "按临床路径执行，用药与随访见下方 anchors 指向的小节。",
        ]
        (S / "text" / f"pathway_{i:02d}.md").write_text("\n".join(body), encoding="utf-8")
        anchors = [
            {"anchor_id": f"{aid}#s2", "kind": "section", "text": "检查项目"},
            {"anchor_id": f"{aid}#s3", "kind": "section", "text": "治疗原则"},
        ]
        card = _card(aid, f"{name}临床路径摘要（合成 {i}）", "text", anchors, {"sections": 3})
        (CARDS / f"{aid}.json").write_text(
            json.dumps(card, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        made += 1
    return made


def gen_table() -> int:
    import openpyxl

    made = 0
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "参考区间"
    ws.append(["检验项目", "单位", "下限", "上限"])
    rows = [
        ("白细胞计数", "10^9/L", 3.5, 9.5),
        ("红细胞计数", "10^12/L", 3.8, 5.1),
        ("血红蛋白", "g/L", 115, 150),
        ("血小板计数", "10^9/L", 100, 300),
    ]
    for r in rows:
        ws.append(list(r))
    xlsx = S / "table" / "reference_ranges.xlsx"
    wb.save(xlsx)
    aid = _aid(3000)
    anchors = [
        {"anchor_id": f"{aid}#t1.r{i}", "kind": "table_row", "text": f"{rows[i - 1][0]} 参考区间"}
        for i in range(1, len(rows) + 1)
    ]
    card = _card(aid, "检验参考区间（合成）", "table", anchors, {"tables": 1, "rows": len(rows)})
    (CARDS / f"{aid}.json").write_text(
        json.dumps(card, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    made += 1

    for i in range(1, 20):
        aid = _aid(3100 + i)
        code, name, dept, checks = DISEASES[i % len(DISEASES)]
        pid = f"MZ{i:03d}"
        lines = ["门诊号,年龄,性别,主诉,诊断,科室,检查项目,日期"]
        lines.append(
            f"{pid},74,男,乏力与腹部不适,{name},{dept},{checks[0]},2026-10-{(i % 28) + 1:02d}"
        )
        (S / "table" / f"menzhen_{i:02d}.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")
        anchors = [{"anchor_id": f"{aid}#t1.r2", "kind": "table_row", "text": f"{name} 门诊记录"}]
        card = _card(aid, f"门诊记录（合成 {i}）", "table", anchors, {"tables": 1, "rows": 1})
        (CARDS / f"{aid}.json").write_text(
            json.dumps(card, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        made += 1
    return made


def gen_image() -> int:
    import pymupdf

    made = 0
    for i in range(1, 21):
        code, name, dept, checks = DISEASES[i % len(DISEASES)]
        aid = _aid(4000 + i)
        doc = pymupdf.open()
        page = doc.new_page(width=595, height=842)
        lines = [
            f"门诊病历（合成样例 {i}）",
            f"姓名：张某某    年龄：7{i % 9}岁    性别：男",
            f"就诊科室：{dept}",
            f"主诉：反复不适 {i % 7 + 1} 天",
            f"诊断：{name}（{code}）",
            f"建议检查：{'、'.join(checks)}",
            f"日期：2026-10-{(i % 28) + 1:02d}",
        ]
        y = 80
        for line in lines:
            try:
                page.insert_text((60, y), line, fontsize=13, fontname="china-s")
            except Exception:  # noqa: BLE001 - 无中文字体时退回 ASCII
                page.insert_text((60, y), line.encode("ascii", "replace").decode(), fontsize=13)
            y += 30
        pix = page.get_pixmap(dpi=120)
        out = S / "image" / f"bingli_{i:02d}.png"
        pix.save(str(out))
        doc.close()
        anchors = [
            {"anchor_id": f"{aid}#img.r1", "kind": "figure_region", "text": "诊断区域"},
            {"anchor_id": f"{aid}#img.r2", "kind": "figure_region", "text": "检查建议区域"},
        ]
        card = _card(
            aid, f"合成门诊病历（{i}）", "image_report", anchors, {"figures": 1, "regions": 2}
        )
        (CARDS / f"{aid}.json").write_text(
            json.dumps(card, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        made += 1
    return made


def main() -> int:
    random.seed(20261031)
    t, b, im = gen_text(), gen_table(), gen_image()
    cards = len(list(CARDS.glob("*.json")))
    print(f"文本 {t} 份 | 表格 {b} 份 | 图文 {im} 份 | 合计 {t + b + im} 份")
    print(f"Asset Card {cards} 张 -> {CARDS.relative_to(ROOT)}")
    return 0 if t >= 20 and b >= 20 and im >= 20 else 1


if __name__ == "__main__":
    raise SystemExit(main())
