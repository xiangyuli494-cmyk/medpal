"""本体版本差分测试（T4 · 4.2）。

全部离线：只用临时 JSONL 文件，不碰数据库、不调 MCP、不联网。

跑：python -m pytest agent/tests/test_ontology_diff.py -q
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent.ontology.diff import (
    DiffVersionInvalid,
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


def test_compared_fields_follow_snapshot_columns(versions: tuple[Path, Path]) -> None:
    """快照只有 7 列，没有 standard —— 本次就比 confidence、anchor_id 与三个内容列。"""
    diff = diff_versions(*versions)

    assert diff["compared_fields"] == [
        "confidence",
        "anchor_id",
        "head_id",
        "rel",
        "tail_id",
    ]


def test_identity_is_triple_id(versions: tuple[Path, Path]) -> None:
    """身份以 schema §4.1 的主键为准，结果里写明用的是哪个键。"""
    diff = diff_versions(*versions)

    assert diff["identity"] == "triple_id"


def test_renumbered_knowledge_is_drift_not_add_remove(tmp_path: Path) -> None:
    """整库重新编号：三条知识内容一模一样，只是 id 全换，不能报成 3 删 3 加。"""
    old = write_jsonl(
        tmp_path / "a.jsonl",
        [
            triple("K27", "requires_exam", "EX-GASTRO", 0.90, "A#p1", "T-aaa00001"),
            triple("K21", "belongs_to_dept", "DEP-GI", 0.88, "A#p2", "T-aaa00002"),
            triple("K29", "has_symptom", "SYM-EPI", 0.70, "A#p3", "T-aaa00003"),
        ],
    )
    new = write_jsonl(
        tmp_path / "b.jsonl",
        [
            triple("K27", "requires_exam", "EX-GASTRO", 0.90, "A#p1", "T-bbb00001"),
            triple("K21", "belongs_to_dept", "DEP-GI", 0.88, "A#p2", "T-bbb00002"),
            triple("K29", "has_symptom", "SYM-EPI", 0.70, "A#p3", "T-bbb00003"),
        ],
    )

    diff = diff_versions(old, new)

    assert diff["counts"] == {"added": 0, "removed": 0, "modified": 0}
    assert len(diff["id_drift"]) == 3


def test_renumbered_pair_still_reports_field_change(tmp_path: Path) -> None:
    """编号换了、置信度也改了：漂移要留痕，改动也不能被吞掉。"""
    old = write_jsonl(
        tmp_path / "a.jsonl",
        [triple("K27", "requires_exam", "EX-GASTRO", 0.90, "A#p1", "T-aaa00001")],
    )
    new = write_jsonl(
        tmp_path / "b.jsonl",
        [triple("K27", "requires_exam", "EX-GASTRO", 0.95, "A#p1", "T-bbb00001")],
    )

    diff = diff_versions(old, new)

    assert diff["counts"] == {"added": 0, "removed": 0, "modified": 1}
    assert len(diff["id_drift"]) == 1
    assert diff["modified"][0]["changed_fields"] == ["confidence"]
    assert diff["modified"][0]["triple_id_old"] == "T-aaa00001"
    assert diff["modified"][0]["triple_id_new"] == "T-bbb00001"


def test_same_id_different_signature_is_modified(tmp_path: Path) -> None:
    """id 没变但头/关系/尾变了：属于语义变更，不能因为 id 相同就当没改。"""
    old = write_jsonl(tmp_path / "a.jsonl", [triple("K27", "requires_exam", "EX-GASTRO", 0.90)])
    new = write_jsonl(tmp_path / "b.jsonl", [triple("K29", "requires_exam", "EX-GASTRO", 0.90)])

    diff = diff_versions(old, new)

    assert diff["counts"] == {"added": 0, "removed": 0, "modified": 1}
    assert diff["modified"][0]["changed_fields"] == ["head_id"]


def test_missing_triple_id_raises(tmp_path: Path) -> None:
    """快照缺主键说明文件坏了，报错要指出是哪一行。"""
    broken = triple("K27", "rel", "EX-1")
    del broken["triple_id"]
    path = write_jsonl(tmp_path / "a.jsonl", [broken])

    with pytest.raises(DiffVersionInvalid) as exc:
        diff_versions(path, path)

    assert "第 1 行" in str(exc.value)


def test_duplicated_triple_id_raises(tmp_path: Path) -> None:
    """主键重复等于快照损坏，不许静默丢一行。"""
    path = write_jsonl(
        tmp_path / "a.jsonl",
        [
            triple("K27", "requires_exam", "EX-GASTRO", triple_id="T-same"),
            triple("K21", "belongs_to_dept", "DEP-GI", triple_id="T-same"),
        ],
    )

    with pytest.raises(DiffVersionInvalid) as exc:
        diff_versions(path, path)

    assert "T-same" in str(exc.value)


def test_absent_standard_does_not_fake_modified(tmp_path: Path) -> None:
    """两侧快照都不带 standard，不能因为「都没有」就算改过。"""
    old = write_jsonl(tmp_path / "a.jsonl", [triple("K27", "rel", "EX-1")])
    new = write_jsonl(tmp_path / "b.jsonl", [triple("K27", "rel", "EX-1", triple_id="T-2")])

    diff = diff_versions(old, new)

    assert diff["counts"] == {"added": 0, "removed": 0, "modified": 0}


def test_report_states_what_was_compared(versions: tuple[Path, Path]) -> None:
    """报告要说清哪个字段没比，别让「无变化」被读成「全都一样」。"""
    old, _ = versions
    text = render_report(diff_versions(old, old))

    assert "比对字段" in text
    assert "standard" in text and "未比对" in text


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
