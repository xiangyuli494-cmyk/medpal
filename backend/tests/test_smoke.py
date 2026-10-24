"""W1 冒烟测试：证明骨架能跑、文档在位、约束没被绕过。

这些用例在 W2 之后仍然保留，它们是「仓库没散架」的最低证明。
"""

from __future__ import annotations

from pathlib import Path


def test_domain_package_imports() -> None:
    from backend.domain import __version__

    assert __version__.startswith("0.")


def test_protocol_doc_has_core_fields(repo_root: Path) -> None:
    text = (repo_root / "docs" / "api" / "ws-protocol.md").read_text(encoding="utf-8")
    for key in ("turn_result", "caption", "escalation", "confidence"):
        assert key in text, f"协议文档缺少字段：{key}"


def test_specs_present(repo_root: Path) -> None:
    required = [
        "docs/specs/access-control.md",
        "docs/specs/data-retention.md",
        "docs/specs/nfr.md",
        "docs/legal/知情同意书.md",
    ]
    missing = [p for p in required if not (repo_root / p).is_file()]
    assert not missing, f"缺少规范文件：{missing}"


def test_guard_words_list_not_empty(repo_root: Path) -> None:
    path = repo_root / "tools" / "guard_words.txt"
    words = [
        line.strip()
        for line in path.read_text(encoding="utf-8-sig").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    assert len(words) >= 14


def test_handoff_template_exists(repo_root: Path) -> None:
    assert (repo_root / "docs" / "handoff" / "模板.md").is_file()
