"""解析器：把一份文件转成 ParsedDoc（blocks + anchors + metadata）。

新增模态只需实现 Parser 并注册到 REGISTRY，主流程不动。
"""
from __future__ import annotations

import csv
import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


@dataclass
class Block:
    kind: str            # heading | paragraph | table_row | figure
    text: str
    locator: dict = field(default_factory=dict)


@dataclass
class ParsedDoc:
    title: str
    modality: str
    blocks: list
    anchors: list
    metadata: dict

    def text(self, max_chars: int = 6000) -> str:
        return "\n".join(b.text for b in self.blocks)[:max_chars]


def _anchor(asset_id_or_path: str, loc: str, kind: str, text: str) -> dict:
    stem = Path(asset_id_or_path).stem
    return {"anchor_id": stem + "#" + loc, "kind": kind, "text": text[:200]}


class Parser(Protocol):
    modality: str
    def accept(self, path: Path) -> bool: ...
    def parse(self, path: Path) -> ParsedDoc: ...


class TextParser:
    modality = "text"

    def accept(self, path: Path) -> bool:
        return path.suffix.lower() in {".txt", ".md"}

    SPLIT = re.compile(r"[。；;!?！？]")

    def parse(self, path: Path) -> ParsedDoc:
        raw = path.read_text(encoding="utf-8", errors="ignore")
        blocks, anchors = [], []
        sec, para = 0, 0
        for line in raw.splitlines():
            s = line.strip()
            if not s:
                continue
            if s.startswith("#"):
                sec += 1
                para = 0
                text = s.lstrip("#").strip()
                blocks.append(Block("heading", text, {"section": sec}))
                anchors.append(_anchor(str(path), "s%d.h" % sec, "section", text))
                continue
            para += 1
            blocks.append(Block("paragraph", s, {"section": sec, "para": para}))
            sent = 0
            for piece in self.SPLIT.split(s):
                piece = piece.strip()
                if len(piece) < 6:
                    continue
                sent += 1
                anchors.append(_anchor(str(path), "s%d.p%d.c%d" % (max(sec, 1), para, sent), "sentence", piece))
        return ParsedDoc(path.stem, self.modality, blocks, anchors, {"chars": len(raw)})


class PdfParser:
    modality = "pdf_text"

    def accept(self, path: Path) -> bool:
        return path.suffix.lower() == ".pdf"

    def parse(self, path: Path) -> ParsedDoc:
        try:
            import fitz  # PyMuPDF
        except ImportError:
            return ParsedDoc(path.stem, self.modality, [], [], {"error": "pymupdf_not_installed"})
        doc = fitz.open(str(path))
        blocks, anchors = [], []
        for pno, page in enumerate(doc, start=1):
            for tno, table in enumerate(page.find_tables(), start=1):
                for rno, row in enumerate(table.extract(), start=1):
                    text = " | ".join("" if c is None else str(c) for c in row)
                    if not text.strip(" |"):
                        continue
                    blocks.append(Block("table_row", text, {"page": pno, "table": tno, "row": rno}))
                    anchors.append(_anchor(str(path), "p%d.t%d.r%d" % (pno, tno, rno), "table_row", text))
            text = page.get_text().strip()
            if text:
                blocks.append(Block("paragraph", text, {"page": pno}))
                anchors.append(_anchor(str(path), "p%d.s1" % pno, "page", text))
        return ParsedDoc(path.stem, self.modality, blocks, anchors, {"pages": doc.page_count})


class TableParser:
    modality = "table"

    def accept(self, path: Path) -> bool:
        return path.suffix.lower() in {".csv", ".xlsx"}

    def parse(self, path: Path) -> ParsedDoc:
        rows = []
        if path.suffix.lower() == ".csv":
            with path.open(encoding="utf-8", errors="ignore", newline="") as f:
                rows = list(csv.reader(f))
        else:
            try:
                import openpyxl
                wb = openpyxl.load_workbook(str(path), read_only=True, data_only=True)
                rows = [[("" if c is None else str(c)) for c in r] for r in wb.active.iter_rows(values_only=True)]
            except ImportError:
                return ParsedDoc(path.stem, self.modality, [], [], {"error": "openpyxl_not_installed"})
        blocks, anchors = [], []
        header = rows[0] if rows else []
        for rno, row in enumerate(rows[1:], start=2):
            text = " | ".join(str(c) for c in row)
            if not text.strip(" |"):
                continue
            blocks.append(Block("table_row", text, {"row": rno}))
            anchors.append(_anchor(str(path), "t1.r%d" % rno, "table_row", text))
        return ParsedDoc(path.stem, self.modality, blocks, anchors,
                         {"rows": max(0, len(rows) - 1), "columns": header})


class ImageReportParser:
    """检验报告单：不训练 OCR，走两条路——① 已有结构化字段（人工/VLM 回填）；
    ② 交给 Nexent 的 analyze-image 技能读图后回填同一结构。"""

    modality = "image_report"

    FIELDS = ["医院", "姓名", "项目", "结果", "参考区间", "单位"]

    def accept(self, path: Path) -> bool:
        return path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}

    def parse(self, path: Path) -> ParsedDoc:
        side = path.with_suffix(path.suffix + ".json")
        blocks, anchors = [], []
        if side.exists():
            import json
            data = json.loads(side.read_text(encoding="utf-8"))
            for i, item in enumerate(data.get("items", []), start=1):
                text = "{} {} {}".format(item.get("name", ""), item.get("value", ""), item.get("range", ""))
                blocks.append(Block("table_row", text, {"region": i}))
                anchors.append(_anchor(str(path), "img.r%d" % i, "image_region", text))
        else:
            blocks.append(Block("figure", path.name, {"whole": True}))
            anchors.append(_anchor(str(path), "img.r1", "image_region", path.name))
        digest = hashlib.sha256(path.read_bytes()).hexdigest()[:12]
        return ParsedDoc(path.stem, self.modality, blocks, anchors,
                         {"sha256_12": digest, "sidecar": side.exists()})


REGISTRY = [TextParser(), PdfParser(), TableParser(), ImageReportParser()]


def pick(path: Path):
    for p in REGISTRY:
        if p.accept(path):
            return p
    return None


def parse(path: str | Path) -> ParsedDoc | None:
    p = Path(path)
    parser = pick(p)
    return parser.parse(p) if parser else None


# 药名/检查名/症状名都要收：实体识别的召回率直接决定能不能连到本体上。
# 顺序按「长的在前」，finditer 才能一次切出完整术语。
ENTITY_HINTS = re.compile(
    r"(消化性溃疡|幽门螺杆菌呼气试验|幽门螺杆菌|胃食管反流病|胃食管反流|上腹部痛|上腹痛|上腹隐痛|上腹不适"
    r"|胃溃疡|胃炎|反酸|烧心|反流|胃镜|呼气试验|布洛芬|阿司匹林|止痛药|NSAIDs|消化内科"
    r"|结石|肺炎|高血压|糖尿病|骨折|贫血)"
)


# 同义词归一：口语说法 -> 本体里的标准写法，供 std_align 与 kg_query 共用
SYNONYMS = {
    "上腹部痛": "上腹隐痛", "上腹痛": "上腹隐痛", "上腹不适": "上腹隐痛", "肚子痛": "上腹隐痛",
    "止痛药": "布洛芬", "NSAIDs": "布洛芬",
    "幽门螺杆菌呼气试验": "幽门螺杆菌", "呼气试验": "幽门螺杆菌",
    "胃食管反流": "胃食管反流病",
    "反酸": "烧心",
}


def guess_entities(doc: ParsedDoc) -> list:
    hits = []
    for b in doc.blocks:
        for m in ENTITY_HINTS.findall(b.text):
            m = SYNONYMS.get(m, m)
            if m not in hits:
                hits.append(m)
    return hits
