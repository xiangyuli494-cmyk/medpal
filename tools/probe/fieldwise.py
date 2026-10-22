"""逐字段抽取原型：一次只问一个字段，替代「一次问全表」。

为什么要改（实测依据）：
- 一次性抽全表时，12 张里有 4 张 JSON 被截断、2 张类型误判、1 张把金额当剂量；
- 单字段问答输出极短，**不可能截断**，字段也不会漂移到别的表格模板上；
- 出错的字段能单独定位，便于人工校对与统计。

用法：
    python tools/probe/fieldwise.py            # 跑全部样本
    python tools/probe/fieldwise.py --only 05  # 只跑 05 处方单
"""
from __future__ import annotations

import argparse
import base64
import glob
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"
OCR_DIR = os.path.join("tools", "probe", "samples", "ocr")
CASES = os.path.join("backend", "tests", "eval", "data", "ocr_cases.json")
MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}
MONEY = ("元", "￥", "¥")
UNITS = ("mg", "g", "ml", "毫升", "片", "粒", "袋", "支", "滴", "克", "毫克", "%")


def ask_one(image_b64: str, mime: str, field: str) -> tuple[str, float]:
    """问一个字段，只要值本身。"""
    prompt = (
        f"这张医院单据上的「{field}」是什么？"
        f"只输出该字段的值本身，不要 JSON、不要引号、不要解释。"
        f"图上没有、看不清、或被遮挡时，只输出两个字符：NONE"
    )
    body = {
        "model": "qwen3.5-ocr",
        "input": {"messages": [{"role": "user", "content": [
            {"image": f"data:{mime};base64,{image_b64}"},
            {"text": prompt},
        ]}]},
    }
    req = urllib.request.Request(
        URL,
        data=json.dumps(body, ensure_ascii=False).encode(),
        headers={
            "Authorization": f"Bearer {os.environ['DASHSCOPE_API_KEY']}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    started = time.perf_counter()
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    text = data["output"]["choices"][0]["message"]["content"][0]["text"].strip()
    return text, (time.perf_counter() - started) * 1000


def clean(value: str, field: str) -> str:
    """模型即使被要求只输出值，仍会回 {"字段": "值"} —— 这里兼容两种形态。"""
    value = re.sub(r"^```[a-z]*|```$", "", value).strip()
    if value.startswith("{"):
        try:
            data = json.loads(value)
        except json.JSONDecodeError:
            data = None
        if isinstance(data, dict):
            inner = data.get("fields") if isinstance(data.get("fields"), dict) else data
            if field in inner:
                value = str(inner[field])
            elif inner:
                value = str(next(iter(inner.values())))
    value = value.strip().strip('"').strip()
    return "" if value.upper() == "NONE" else value


HEADER_WORDS = {
    "项目", "结果", "金额", "剂量", "科室", "医生", "时间", "数量", "药品名称",
    "总费用", "医保支付", "自付", "诊断", "用药", "部位", "主诉", "参考区间",
    "频次", "疗程", "姓名", "性别", "年龄",
}
BLOCK_WORDS = ("门诊药房取药", "出院后用药及建议", "其他诊断", "检验申请单", "检查申请单")
PURE_UNIT = {"元", "￥", "¥", "元，", "元。", "元,", "元."}


def judge(field: str, value: str) -> str:
    """返回 OK / 空 / 垃圾原因 / 致命原因。实测出来的垃圾形态都在这儿拦住。"""
    if not value:
        return "空"
    v = value.strip()
    if field == "剂量":
        if any(mark in v for mark in MONEY):
            return f"致命:剂量含金额({v})"
        if not any(unit in v.lower() for unit in UNITS):
            return f"致命:剂量缺单位({v})"
    if v in HEADER_WORDS:
        return "垃圾:表头当值"
    if v in PURE_UNIT:
        return "垃圾:纯单位碎片"
    if any(block in v for block in BLOCK_WORDS) and len(v) < 20:
        return "垃圾:区块名当值"
    return "OK"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", default="", help="只跑编号前缀，如 05")
    args = parser.parse_args(argv[1:])

    cases = {c["id"].split("-")[1]: c for c in json.load(open(CASES, encoding="utf-8"))}
    files = sorted(p for p in glob.glob(os.path.join(OCR_DIR, "*"))
                   if p.lower().endswith((".png", ".jpg")) and "synth" not in p)
    if args.only:
        files = [f for f in files if os.path.basename(f)[:2] == args.only]

    total_fields = ok_fields = fatal = empty = junk = 0
    print(f"{'文件':26} {'字段':8} {'值':22} 判定")
    for path in files:
        num = os.path.basename(path)[:2]
        case = cases.get(num)
        if not case:
            continue
        mime = MIME[os.path.splitext(path)[1].lower()]
        b64 = base64.b64encode(open(path, "rb").read()).decode()
        for field in case["required_fields"]:
            total_fields += 1
            try:
                raw, _ms = ask_one(b64, mime, field)
            except urllib.error.HTTPError as exc:
                print(f"{os.path.basename(path):26} {field:8} {'':22} HTTP {exc.code}")
                continue
            value = clean(raw, field)
            verdict = judge(field, value)
            ok_fields += 1 if verdict == "OK" else 0
            empty += 1 if verdict == "空" else 0
            fatal += 1 if verdict.startswith("致命") else 0
            junk += 1 if verdict.startswith("垃圾") else 0
            print(f"{os.path.basename(path):26} {field:8} {value[:22]:22} {verdict}")

    print(f"\n字段总数 {total_fields}：可用 {ok_fields}（{ok_fields/max(total_fields,1)*100:.0f}%）"
          f" / 空 {empty} / 垃圾 {junk} / 致命 {fatal}")
    print("说明：本表只统计「抽到值且通过硬规则」，不代表与原文一致——一致性需要人工标注后再算。")
    return 0 if fatal == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
