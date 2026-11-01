"""文本型 PDF 解析：按小节分段，每段带页码锚点（赛题3 W1 任务 5.1）。

锚点编码遵循 `agent/docs/mcp-contract.md` §1.2 的 pdf_text 规则：
- 整节：`<asset_id>#p{页}.s{小节序号}`
- 表格行：`<asset_id>#p{页}.t{表}.r{行}`

只依赖 PyMuPDF；不引入 OCR，扫描件走 5.7 的 ocr.py。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

SECTION_RE = re.compile(
    r"^\s*(?:第[一二三四五六七八九十百\d]+[章节部分]"
    r"|\d+(?:\.\d+)*[\s、.]+"
    r"|[一二三四五六七八九十]+、)"
)
MIN_SECTION_CHARS = 8


@dataclass
class Block:
    kind: str                      # section | paragraph | table_row
    text: str
    page: int                      # 1-based
    anchor_id: str = ""


@dataclass
class ParsedPdf:
    asset_id: str
    modality: str = "pdf_text"
    page_count: int = 0
    blocks: list[Block] = field(default_factory=list)

    @property
    def anchors(self) -> list[dict]:
        return [{"anchor_id": b.anchor_id, "kind": b.kind, "text": b.text}
                for b in self.blocks if b.anchor_id]

    @property
    def sections(self) -> list[Block]:
        return [b for b in self.blocks if b.kind == "section"]


def _is_heading(line: str) -> bool:
    s = line.strip()
    return bool(s) and len(s) <= 40 and bool(SECTION_RE.match(s))


def parse_pdf(path: str | Path, asset_id: str = "AST-2026-000001") -> ParsedPdf:
    """解析文本型 PDF，返回按页与小节切分的块，每块带锚点。"""
    import fitz  # 延迟导入：未装 PyMuPDF 时本模块仍可 import

    doc = fitz.open(str(path))
    out = ParsedPdf(asset_id=asset_id, page_count=doc.page_count)
    sec_no = 0
    for page_idx in range(doc.page_count):
        page_no = page_idx + 1
        text = doc[page_idx].get_text("text")
        current: list[str] = []
        for raw in text.splitlines():
            line = raw.strip()
            if not line:
                continue
            if _is_heading(line):
                if current:
                    body = "\n".join(current).strip()
                    if len(body) >= MIN_SECTION_CHARS:
                        out.blocks.append(Block("paragraph", body, page_no,
                                                f"{asset_id}#p{page_no}.s{sec_no}"))
                    current = []
                sec_no += 1
                out.blocks.append(Block("section", line, page_no,
                                        f"{asset_id}#p{page_no}.s{sec_no}"))
            else:
                current.append(line)
        if current:
            body = "\n".join(current).strip()
            if len(body) >= MIN_SECTION_CHARS:
                out.blocks.append(Block("paragraph", body, page_no,
                                        f"{asset_id}#p{page_no}.s{sec_no or 1}"))
        # 表格行锚点（无表则跳过）
        try:
            tables = doc[page_idx].find_tables()
        except Exception:  # noqa: BLE001 - 老版本 PyMuPDF 无 find_tables
            tables = None
        for t_idx, table in enumerate(getattr(tables, "tables", []) or [], start=1):
            for r_idx, row in enumerate(table.extract(), start=1):
                cells = [c for c in row if c]
                if not cells:
                    continue
                out.blocks.append(Block("table_row", " | ".join(cells), page_no,
                                        f"{asset_id}#p{page_no}.t{t_idx}.r{r_idx}"))
    doc.close()
    return out
