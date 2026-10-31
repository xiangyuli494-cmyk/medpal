"""5.1 验收：20 页 PDF 按小节分段，每段带页码锚点。

PyMuPDF 缺失时跳过 PDF 用例；纯逻辑用例始终执行。
"""
from __future__ import annotations

import re

import pytest

from agent.parse.pdf import _is_heading

ANCHOR_RE = re.compile(r"^AST-\d{4}-[0-9a-f]{6}#p\d+\.(s\d+|t\d+\.r\d+)$")


def test_heading_detection() -> None:
    assert _is_heading("第3章 消化性溃疡")
    assert _is_heading("一、诊断依据")
    assert _is_heading("2.1 检查项目")
    body = "This body paragraph is longer than forty characters so it is not a heading"
    assert not _is_heading(body)


def test_anchor_pattern_matches_contract() -> None:
    for anchor in ("AST-2026-000137#p3.s1", "AST-2026-000137#p3.t1.r2"):
        assert ANCHOR_RE.match(anchor), anchor
    for bad in ("AST-2026-000137#s2.p1.c3", "p3.t1.r2", "AST-2026#p1.s1"):
        assert not ANCHOR_RE.match(bad), bad


fitz = pytest.importorskip("fitz", reason="未安装 PyMuPDF")


def _make_pdf(path, pages: int = 20) -> None:
    doc = fitz.open()
    for i in range(1, pages + 1):
        page = doc.new_page()
        page.insert_text((72, 90), f"{i}.1 Chapter Title", fontsize=16)
        page.insert_text((72, 130), f"Body text of page {i} for section split.", fontsize=11)
    doc.save(str(path))
    doc.close()


def test_twenty_pages_and_sections(tmp_path) -> None:
    from agent.parse.pdf import parse_pdf

    pdf = tmp_path / "sample.pdf"
    _make_pdf(pdf)
    doc = parse_pdf(pdf, asset_id="AST-2026-000137")
    assert doc.page_count == 20
    assert len(doc.sections) == 20
    assert {b.page for b in doc.blocks} == set(range(1, 21))


def test_every_block_has_valid_anchor(tmp_path) -> None:
    from agent.parse.pdf import parse_pdf

    pdf = tmp_path / "s.pdf"
    _make_pdf(pdf, pages=3)
    doc = parse_pdf(pdf, asset_id="AST-2026-000137")
    assert doc.anchors
    for item in doc.anchors:
        assert ANCHOR_RE.match(item["anchor_id"]), item["anchor_id"]
