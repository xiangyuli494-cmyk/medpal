"""评测集数据的结构校验（不联网、不花费用）。

作用：把「数据集本身对不对」纳入 CI。真实评测（跑 ASR/OCR 比对结果）要等样本录进来，
但结构错误、把真实患者信息写进仓库、剂量用例漏标——这些现在就能拦住。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

EVAL_DIR = Path(__file__).resolve().parent
DATA_DIR = EVAL_DIR / "data"

ASR_REQUIRED_CATEGORIES = {"正常语速", "方言口音", "背景广播声", "老人含糊"}
OCR_REQUIRED_DOC_TYPES = {
    "挂号单",
    "门诊病历首页",
    "检验申请单",
    "检验报告",
    "处方单",
    "缴费凭证",
    "检查申请单",
    "取药单",
    "出院小结",
    "医保结算单",
}
# 只有这三类单据含剂量，必须标 dose_check（红线：剂量错误数恒为 0）
DOSE_DOC_TYPES = {"处方单", "取药单", "出院小结"}
# 简版 PII 探测：身份证 18 位、手机号 11 位
PII_PATTERNS = (re.compile(r"\d{17}[\dXx]"), re.compile(r"1[3-9]\d{9}"))


def load(name: str) -> list[dict]:
    path = DATA_DIR / name
    assert path.is_file(), f"缺少数据集 {path}"
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def asr_cases() -> list[dict]:
    return load("asr_cases.json")


@pytest.fixture(scope="module")
def ocr_cases() -> list[dict]:
    return load("ocr_cases.json")


def test_asr_dataset_structure(asr_cases: list[dict]) -> None:
    assert len(asr_cases) == 20, "ASR 起步集应为 20 条（四类各 5 条）"
    ids = [case["id"] for case in asr_cases]
    assert len(ids) == len(set(ids)), "用例 id 必须唯一"
    for case in asr_cases:
        assert case["expected_text"].strip(), f"{case['id']} 缺 expected_text"
        assert case["keywords"], f"{case['id']} 缺关键词"
        assert case["audio"].startswith("samples/asr/"), f"{case['id']} 音频路径不合规范"


def test_asr_dataset_covers_four_categories(asr_cases: list[dict]) -> None:
    counts: dict[str, int] = {}
    for case in asr_cases:
        counts[case["category"]] = counts.get(case["category"], 0) + 1
    assert set(counts) == ASR_REQUIRED_CATEGORIES, f"类别不全：{sorted(counts)}"
    assert all(count == 5 for count in counts.values()), f"每类应各 5 条，实际 {counts}"


def test_ocr_dataset_structure(ocr_cases: list[dict]) -> None:
    assert len(ocr_cases) == 10, "OCR 起步集应为 10 类单据"
    ids = [case["id"] for case in ocr_cases]
    assert len(ids) == len(set(ids)), "用例 id 必须唯一"
    doc_types = {case["doc_type"] for case in ocr_cases}
    assert doc_types == OCR_REQUIRED_DOC_TYPES, f"单据类型与选型文档不一致：{sorted(doc_types)}"


def test_ocr_dose_cases_are_flagged(ocr_cases: list[dict]) -> None:
    flagged = {case["doc_type"] for case in ocr_cases if case.get("dose_check")}
    expected = sorted(DOSE_DOC_TYPES)
    assert flagged == DOSE_DOC_TYPES, f"剂量专项应覆盖 {expected}，实际 {sorted(flagged)}"
    for case in ocr_cases:
        if case.get("dose_check"):
            assert "剂量" in case["required_fields"], f"{case['id']} 标了剂量专项却没有剂量字段"


def test_dataset_has_no_pii(asr_cases: list[dict], ocr_cases: list[dict]) -> None:
    """合规红线：仓库内不得出现身份证号或手机号（10 号 §375）。"""
    text = json.dumps(asr_cases + ocr_cases, ensure_ascii=False)
    for pattern in PII_PATTERNS:
        hit = pattern.search(text)
        assert hit is None, f"数据集中出现疑似 PII：{hit.group() if hit else ''}"


def test_audio_files_absent_is_allowed(asr_cases: list[dict]) -> None:
    """录音不进仓库（.gitignore 忽略 *.wav），所以这里只校验路径声明，不断言文件存在。"""
    missing = [case["id"] for case in asr_cases if not (EVAL_DIR / case["audio"]).exists()]
    assert len(missing) == len(asr_cases), "样本目录若被提交进仓库，说明 .gitignore 失效，需排查"
