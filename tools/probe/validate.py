"""OCR 输出校验器：把「模型说了什么」和「我们允许它说什么」分开。

为什么需要它（都是实测踩出来的）：
1. 提示词里的字段白名单不生效——模型会输出户籍表式的键（姓名/血型/兵役状况）；
2. 一次全表抽取容易把金额当剂量（实测 08_取药单 抽出 "剂量: 14.54元"），这是红线级错误；
3. 长单据输出会被截断，JSON 解析失败；
4. 模型会照抄提示词里的示例值，产生看似真实其实虚构的字段。

本文件只做校验，不发请求：调用方拿到模型输出后必须先过这里，再决定是否落库。
定位：评测与适配器层共用（W1 放 tools/probe/，W5 迁入 backend/adapters/ocr/）。

用法：
    python tools/probe/validate.py --selftest        # 自测（不联网）
    python tools/probe/validate.py --json-file x.json
退出码：0 通过（可能有警告）；1 有致命问题；2 输入无法解析。
"""
from __future__ import annotations

import argparse
import json
import re
import sys

VALID_DOC_TYPES = {
    "挂号单", "门诊病历首页", "检验申请单", "检验报告", "处方单",
    "缴费凭证", "检查申请单", "取药单", "出院小结", "医保结算单", "unknown",
}

ALLOWED_FIELDS = {
    "科室", "医生", "时间", "项目", "结果", "参考区间",
    "药品名称", "剂量", "频次", "疗程", "数量",
    "金额", "总费用", "医保支付", "自付",
    "主诉", "诊断", "用药", "部位",
}

TOP_KEYS = {"doc_type", "fields", "uncertain_fields", "notes"}

# 出现即判致命：这些是别的表格的字段，也是编造证号的高危面
BANNED_KEY_PARTS = (
    "姓名", "性别", "年龄", "身份证", "出生日期", "住址", "电话", "民族",
    "籍贯", "血型", "文化程度", "婚姻", "兵役", "宗教", "职业", "收入", "身高",
)

MONEY_MARKS = ("元", "￥", "¥", "金额")
UNIT_TOKENS = ("mg", "g", "ml", "毫升", "片", "粒", "袋", "支", "滴", "u", "iu", "%", "克", "毫克")


def _strip_fence(text: str) -> str:
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    return (m.group(1) if m else text).strip()


def parse(text: str) -> dict:
    """模型输出 → dict。剥掉代码块围栏，容忍尾随噪声。"""
    raw = _strip_fence(text)
    if not raw.startswith("{"):
        start = raw.find("{")
        if start < 0:
            raise ValueError("输出里没有 JSON 对象")
        raw = raw[start:]
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # 截断是最常见的失败形态：报出来，不猜
        raise ValueError("JSON 不完整（很可能是输出被截断，需要设 max_tokens）")


def validate(payload: object) -> tuple[list[str], list[str]]:
    """返回 (致命问题, 警告)。致命问题非空则不得落库。"""
    critical: list[str] = []
    warning: list[str] = []

    if not isinstance(payload, dict):
        return ["顶层不是 JSON 对象"], []

    extra_top = set(payload) - TOP_KEYS
    if extra_top:
        warning.append(f"顶层多出键：{sorted(extra_top)}")

    doc_type = str(payload.get("doc_type", ""))
    if doc_type not in VALID_DOC_TYPES:
        warning.append(f"doc_type 不在枚举内：{doc_type!r}")

    fields = payload.get("fields") or {}
    if not isinstance(fields, dict):
        return ["fields 不是对象"], warning

    uncertain = payload.get("uncertain_fields") or []
    if not isinstance(uncertain, list):
        uncertain = []

    for key, value in fields.items():
        if any(bad in key for bad in BANNED_KEY_PARTS):
            critical.append(f"出现禁用字段：{key}")
        if key not in ALLOWED_FIELDS:
            warning.append(f"字段不在白名单（应丢弃）：{key}")
        text = "" if value is None else str(value).strip()
        if not text:
            continue
        if key == "剂量":
            if any(mark in text for mark in MONEY_MARKS):
                critical.append(f"剂量字段里出现金额：{key}={text!r}")
            elif not any(tok in text.lower() for tok in UNIT_TOKENS):
                critical.append(f"剂量字段缺少单位：{key}={text!r}")
        if "?" in text and key not in uncertain:
            warning.append(f"值为 ? 但未登记到 uncertain_fields：{key}")

    for name in uncertain:
        if name not in fields:
            warning.append(f"uncertain_fields 里的键不在 fields 中：{name}")

    return critical, warning


def selftest() -> int:
    cases = [
        ("正常处方",
         {"doc_type": "处方单",
          "fields": {"药品名称": "替硝唑片", "剂量": "0.5G", "频次": "每日一次"},
          "uncertain_fields": []},
         0),
        ("户籍字段混入",
         {"doc_type": "挂号单", "fields": {"血型": "A", "科室": "内科"}, "uncertain_fields": []},
         1),
        ("金额误当剂量",
         {"doc_type": "取药单", "fields": {"剂量": "14.54元"}, "uncertain_fields": []},
         1),
        ("剂量缺单位",
         {"doc_type": "处方单", "fields": {"剂量": "100"}, "uncertain_fields": []},
         1),
        ("类型不在枚举（仅警告）",
         {"doc_type": "发票", "fields": {"金额": "6841.90"}, "uncertain_fields": []},
         0),
        ("问号未登记（仅警告）",
         {"doc_type": "检验报告", "fields": {"结果": "?"}, "uncertain_fields": []},
         0),
    ]
    failed = 0
    for name, payload, expect in cases:
        critical, warning = validate(payload)
        code = 1 if critical else 0
        ok = code == expect
        failed += 0 if ok else 1
        print(f"[{'OK' if ok else 'FAIL'}] {name}: 致命 {len(critical)} / 警告 {len(warning)}")
        for item in critical:
            print(f"      致命: {item}")
    try:
        parse("```json\n{\"doc_type\": \"处方单\"}\n```")
        parse('{"doc_type": "处方单", "fields": {"剂量": "0.5G"')
        print("[FAIL] 截断检测：不完整 JSON 应当报错")
        failed += 1
    except ValueError:
        print("[OK] 截断检测：不完整 JSON 正确报错")
    print(f"\n自测结果：{'全部通过' if failed == 0 else str(failed) + ' 项失败'}")
    return 0 if failed == 0 else 1


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="OCR 输出校验器")
    parser.add_argument("--json-file", default="", help="要校验的 JSON 文件")
    parser.add_argument("--selftest", action="store_true", help="跑内置用例，不联网")
    args = parser.parse_args(argv[1:])

    if args.selftest:
        return selftest()
    if not args.json_file:
        return selftest()

    try:
        payload = json.loads(open(args.json_file, encoding="utf-8").read())
    except (OSError, json.JSONDecodeError) as exc:
        print(f"输入无法解析：{exc}", file=sys.stderr)
        return 2

    critical, warning = validate(payload)
    for item in critical:
        print(f"致命: {item}")
    for item in warning:
        print(f"警告: {item}")
    verdict = "不通过" if critical else "通过"
    print(f"\n结论：{verdict}（致命 {len(critical)} / 警告 {len(warning)}）")
    return 1 if critical else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
