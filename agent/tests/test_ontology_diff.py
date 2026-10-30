"""本体版本差分测试（T4 · 4.2）。

全部离线：只用临时 JSONL 文件，不碰数据库、不调 MCP、不联网。

跑：python -m pytest agent/tests/test_ontology_diff.py -q
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent.ontology.diff import (
    DiffVersionNotFound,
    diff_versions,
    render_report,
)


def write_jsonl(path: Path, rows: list[dict]) -> Path:
    payload = "\n".join(json.dumps(r, ensure_ascii=False) for r in rows)
    path.write_text(payload + "\n", encoding="utf-8")
    return path


def triple(
    head: str,
    rel: str,
    tail: str,
    confidence: float = 0.9,
    anchor: str = "A#p1",
    triple_id: str = "T-00000001",
    standard: dict | None = None,
) -> dict:
    row = {
        "triple_id": triple_id,
        "head_id": head,
        "rel": rel,
        "tail_id": tail,
        "confidence": confidence,
        "asset_id": "AST-2026-000137",
        "anchor_id": anchor,
    }
    if standard is not None:
        row["standard"] = standard
    return row


@pytest.fixture()
def versions(tmp_path: Path) -> tuple[Path, Path]:
    """v0.9 四条；v1.0 删一条、加一条、改两条、留一条不动。"""
    old_rows = [
        triple("K27", "requires_exam", "EX-GASTRO", 0.90, "A#s3.p1.c2", "T-00000001"),
        triple("K21", "belongs_to_dept", "DEP-GI", 0.88, "A#s1.h", "T-00000002"),
        triple("K29", "has_symptom", "SYM-EPI", 0.70, "A#s2.p1.c2", "T-00000003"),
        triple("K27", "requires_exam", "EX-HP-BT", 0.92, "A#s3.p1.c1", "T-00000004"),
    ]
    new_rows = [
        triple("K27", "requires_exam", "EX-GASTRO", 0.95, "A#s3.p1.c2", "T-00000001"),
        triple("K21", "belongs_to_dept", "DEP-GI", 0.88, "A#s2.p1.c2", "T-00000002"),
        triple("K27", "requires_exam", "EX-HP-BT", 0.92, "A#s3.p1.c1", "T-00000004"),
        triple("K30", "causes", "K27", 0.90, "B#p2", "T-00000005"),
    ]
    return (
        write_jsonl(tmp_path / "ontology_v0.9.jsonl", old_rows),
        write_jsonl(tmp_path / "ontology_v1.0.jsonl", new_rows),
    )


def test_counts_three_categories(versions: tuple[Path, Path]) -> None:
    diff = diff_versions(*versions)

    assert diff["counts"] == {"added": 1, "removed": 1, "modified": 2}
    assert [r["head"]["id"] for r in diff["added"]] == ["K30"]
    assert [r["tail"]["id"] for r in diff["removed"]] == ["SYM-EPI"]


def test_record_shape_matches_schema(versions: tuple[Path, Path]) -> None:
    """对外字段按 ontology-schema.md §4.2：head/tail 嵌套、锚点在 provenance 里。"""
    diff = diff_versions(*versions)
    added = diff["added"][0]

    assert set(added) == {"triple_id", "head", "rel", "tail", "confidence", "provenance"}
    assert added["head"] == {"id": "K30"}
    assert added["tail"] == {"id": "K27"}
    assert added["provenance"] == {
        "asset_id": "AST-2026-000137",
        "anchor_id": "B#p2",
    }
    # 快照没有 type/label，不许凭空造出来
    assert "type" not in added["head"]
    assert "label" not in added["head"]


def test_modified_carries_changed_fields(versions: tuple[Path, Path]) -> None:
    diff = diff_versions(*versions)
    by_key = {(r["head"]["id"], r["rel"], r["tail"]["id"]): r for r in diff["modified"]}

    assert by_key[("K27", "requires_exam", "EX-GASTRO")]["changed_fields"] == ["confidence"]
    assert by_key[("K21", "belongs_to_dept", "DEP-GI")]["changed_fields"] == ["anchor_id"]


def test_identical_versions_report_nothing(versions: tuple[Path, Path]) -> None:
    """两边都有且三字段全同，不能算「改」——否则重建一次会报满屏噪音。"""
    old, _ = versions
    diff = diff_versions(old, old)

    assert diff["counts"] == {"added": 0, "removed": 0, "modified": 0}


def test_standard_change_is_modified(tmp_path: Path) -> None:
    old = write_jsonl(
        tmp_path / "a.jsonl",
        [triple("K27", "aligned_to_standard", "ICD10-K27", 0.99, "A#p1", "T-1")],
    )
    new = write_jsonl(
        tmp_path / "b.jsonl",
        [
            triple(
                "K27",
                "aligned_to_standard",
                "ICD10-K27",
                0.99,
                "A#p1",
                "T-1",
                standard={"scheme": "ICD-10", "code": "K27.9"},
            )
        ],
    )

    diff = diff_versions(old, new)

    assert diff["counts"]["modified"] == 1
    assert diff["modified"][0]["changed_fields"] == ["standard"]


def test_missing_version_raises(tmp_path: Path) -> None:
    """文件不存在必须报错，不许静默返回空结果。"""
    old = write_jsonl(tmp_path / "a.jsonl", [triple("K27", "rel", "EX-1")])

    with pytest.raises(DiffVersionNotFound):
        diff_versions(old, tmp_path / "not_exists.jsonl")


def test_triple_id_drift_is_not_modified(tmp_path: Path) -> None:
    """知识没变、只是数据库编号换了：不算改，但要留痕。"""
    old = write_jsonl(tmp_path / "a.jsonl", [triple("K27", "rel", "EX-1", triple_id="T-old")])
    new = write_jsonl(tmp_path / "b.jsonl", [triple("K27", "rel", "EX-1", triple_id="T-new")])

    diff = diff_versions(old, new)

    assert diff["counts"] == {"added": 0, "removed": 0, "modified": 0}
    assert diff["id_drift"] == [
        {
            "head": {"id": "K27"},
            "rel": "rel",
            "tail": {"id": "EX-1"},
            "triple_id_old": "T-old",
            "triple_id_new": "T-new",
        }
    ]


def test_report_is_human_readable(versions: tuple[Path, Path]) -> None:
    diff = diff_versions(*versions)
    text = render_report(diff)

    assert "新增 1" in text and "删除 1" in text and "修改 2" in text
    assert "K30" in text
    assert "confidence" in text
    assert "anchor_id" in text


def test_report_on_no_change(versions: tuple[Path, Path]) -> None:
    old, _ = versions
    text = render_report(diff_versions(old, old))

    assert "无变化" in text
