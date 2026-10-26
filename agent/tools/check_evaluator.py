"""本地复刻 Nexent v2.8.0 的 Code 评估器校验（四道闸），离线验证评估器可用。

真实校验器在 Nexent 服务端：
  backend/management/services/evaluation/scoring.py:57  validate_code_evaluator()
  backend/management/services/evaluation/common.py     ALLOWED_BUILTINS
  sdk/nexent/core/agents/sandbox.py:872                _scan_shell_calls()

本文件把这三处的规则**逐条照抄**过来，只为在没有 Nexent 控制台的情况下证明
「我们写的评估器能通过官方校验」。它不是官方实现，差异见文末 KNOWN_GAPS。

用法：
    python agent/tools/check_evaluator.py            # 跑全部检查
    python agent/tools/check_evaluator.py -v         # 附带每条用例的 reason
"""

from __future__ import annotations

import ast
import inspect
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVALUATOR = ROOT / "agent" / "eval" / "nexent_code_evaluator.py"
EVALUATOR_FILENAME = "<evaluator>"

# ---------------------------------------------------------------------------
# 以下三段从 Nexent 源码逐字照抄
# ---------------------------------------------------------------------------

# 源：backend/management/services/evaluation/common.py:18-52
ALLOWED_BUILTINS = {
    "int": int, "float": float, "str": str, "bool": bool,
    "list": list, "dict": dict, "tuple": tuple, "set": set,
    "abs": abs, "round": round, "min": min, "max": max, "sum": sum, "pow": pow,
    "len": len, "range": range, "sorted": sorted, "reversed": reversed,
    "enumerate": enumerate, "zip": zip, "map": map, "filter": filter,
    "any": any, "all": all, "isinstance": isinstance,
    "True": True, "False": False, "None": None,
    "Exception": Exception, "ValueError": ValueError, "TypeError": TypeError,
    "KeyError": KeyError, "IndexError": IndexError, "AttributeError": AttributeError,
}

# 源：sdk/nexent/core/agents/sandbox.py:819-828
FORBIDDEN_SHELL_CALLS = {
    "subprocess": {
        "run", "call", "check_call", "check_output",
        "Popen", "getoutput", "getstatusoutput",
    },
    "os": {
        "system", "popen", "execv", "execve", "execvp",
        "spawnl", "spawnv", "spawnlp", "spawnvp",
    },
}


# 源：sdk/nexent/core/agents/sandbox.py:872-929（去掉 pip install 豁免分支）
def scan_shell_calls(code: str) -> list[str]:
    stripped_lines = [line.strip() for line in code.splitlines() if line.strip()]
    violations: list[str] = []
    for line in stripped_lines:
        if line.startswith("!"):
            violations.append("IPython shell escape (!...)")
        elif re.match(r"^%(?:system|sx|sc)\b", line, flags=re.IGNORECASE):
            violations.append("IPython shell magic")
        elif re.match(r"^%%(?:bash|sh|script)\b", line, flags=re.IGNORECASE):
            violations.append("IPython shell cell magic")

    try:
        tree = ast.parse(code)
    except SyntaxError:
        return violations

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute):
            attr = func.attr
            if isinstance(func.value, ast.Name):
                module = func.value.id
                if module in FORBIDDEN_SHELL_CALLS and attr in FORBIDDEN_SHELL_CALLS[module]:
                    violations.append(f"{module}.{attr}(...)")
            if (
                isinstance(func.value, ast.Call)
                and isinstance(func.value.func, ast.Name)
                and func.value.func.id == "get_ipython"
                and attr in {"system", "getoutput"}
            ):
                violations.append(f"get_ipython().{attr}(...)")
    return violations


# 源：backend/management/services/evaluation/scoring.py:30-55
def scan_evaluator_introspection(code: str) -> list[str]:
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []
    violations = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            violations.append(f"dunder attribute access .{node.attr}")
        elif isinstance(node, ast.Name) and node.id.startswith("__"):
            violations.append(f"dunder name {node.id!r}")
    return violations


# 源：backend/management/services/evaluation/scoring.py:57-198，四道闸
class Rejected(Exception):
    pass


def validate_code_evaluator(code: str) -> dict:
    """照抄官方四道闸。返回 {"stage": 停在/通过的闸, "sig": 签名或 None}。"""
    # 闸 1：语法
    try:
        compile(code, EVALUATOR_FILENAME, "exec")
    except SyntaxError as e:
        raise Rejected(f"[闸1 语法] line {e.lineno}: {e.msg}")

    # 闸 2：AST 扫描
    violations = scan_shell_calls(code) + scan_evaluator_introspection(code)
    if violations:
        raise Rejected("[闸2 AST] 禁止操作: " + ", ".join(violations))

    # 闸 3：白名单 exec
    local_vars: dict = {}
    try:
        exec(compile(code, EVALUATOR_FILENAME, "exec"),
             {"__builtins__": ALLOWED_BUILTINS, "json": json},
             local_vars)
    except NameError as e:
        raise Rejected(f"[闸3 白名单] 未定义/被禁名: {e}")
    except Exception as e:  # noqa: BLE001
        raise Rejected(f"[闸3 执行] {type(e).__name__}: {e}")

    # 闸 4：签名
    fn = local_vars.get("evaluate")
    if not callable(fn):
        raise Rejected("[闸4 签名] 没有可调用的 evaluate")
    try:
        sig = inspect.signature(fn)
    except (TypeError, ValueError):
        return {"stage": "passed(签名不可内省)", "sig": None, "fn": fn, "g": local_vars}

    required = ["query", "expected", "actual", "runtime_events"]
    params = sig.parameters
    has_var_keyword = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values())
    missing = [n for n in required if n not in params]
    if missing and not has_var_keyword:
        raise Rejected("[闸4 签名] 缺少参数: " + ", ".join(missing))
    return {"stage": "passed", "sig": str(sig), "fn": fn, "g": local_vars}


def run_evaluator(code: str, query: str, expected: str, actual: str) -> dict:
    """照抄 scoring.py:611 _run_code_evaluators 的运行时调用方式（全关键字传参）。"""
    g: dict = {}
    exec(compile(code, EVALUATOR_FILENAME, "exec"),
         {"__builtins__": ALLOWED_BUILTINS, "json": json}, g)
    fn = g["evaluate"]
    return fn(query=query, expected=expected, actual=actual, runtime_events=[])


# ---------------------------------------------------------------------------
# 正例：我们的评估器必须通过四闸
# ---------------------------------------------------------------------------

GOLD = json.dumps({
    "department": "消化内科",
    "exams": ["胃镜", "幽门螺杆菌检测"],
    "trace_completeness": 0.75,
}, ensure_ascii=False)

FUNC_CASES = [
    ("全对", 1.0, "科室：消化内科\n检查项：胃镜、幽门螺杆菌检测\n完整率：0.75\n"),
    ("少一个检查项", 0.85, "科室：消化内科\n检查项：胃镜\n完整率：0.75\n"),
    ("带 markdown 与列表符", 1.0,
     "## 结论\n- **科室：消化内科**\n- **检查项：胃镜、幽门螺杆菌检测**\n- **完整率：0.75**\n"),
    ("科室错+完整率低", 0.0, "科室：心血管内科\n检查项：心电图\n完整率：0.4\n"),
    ("缺完整率字段", 0.8, "科室：消化内科\n检查项：胃镜、幽门螺杆菌检测\n"),
    ("空回答", 0.0, ""),
]


# 反例：这些必须被拒（证明复刻的闸有牙）
_RET_OK = "    return {'score': 1, 'reason': 'x'}\n"
_RET_DUNDER = "    return {'score': 1, 'reason': str(__builtins__)}\n"


def _fn(body: str = "    pass\n", ret: str = _RET_OK) -> str:
    """包一个签名合格的 evaluate；body 是函数体，ret 是返回值行。"""
    return "def evaluate(**kwargs):\n" + body + ret


NEG_CASES = [
    ("import os", "import os\n\n" + _fn()),
    ("subprocess.run", "import subprocess\n\n" + _fn("    subprocess.run(['ls'])\n")),
    ("os.system", _fn("    os.system('id')\n")),
    ("dunder 属性逃逸", _fn("    x = ().__class__.__base__\n")),
    ("dunder 名字 __builtins__", _fn(ret=_RET_DUNDER)),
    ("顶层 open()", "open('x.txt')\n\n" + _fn()),
    ("顶层 class 定义", "class A:\n    pass\n\n" + _fn()),
]


def main() -> int:
    verbose = "-v" in sys.argv
    code = EVALUATOR.read_text(encoding="utf-8")
    failures: list[str] = []

    print("=" * 72)
    print("被测文件:", EVALUATOR.relative_to(ROOT))
    print("行数:", len(code.splitlines()), " 字节:", len(code.encode("utf-8")))
    print("=" * 72)

    # --- A. 四道闸 ---
    print("\n[A] 官方四道闸（照抄 scoring.py:57 validate_code_evaluator）")
    try:
        info = validate_code_evaluator(code)
        print("  [PASS]", info["stage"], "| sig =", info["sig"])
    except Rejected as e:
        print("  [FAIL]", e)
        failures.append("四道闸")
        info = None

    # --- B. 反例必须被拒 ---
    print("\n[B] 反例（必须被拒，否则说明复刻没牙）")
    for name, snippet in NEG_CASES:
        try:
            validate_code_evaluator(snippet)
            print(f"  [FAIL] {name}: 竟然通过了")
            failures.append("反例放行:" + name)
        except Rejected as e:
            print(f"  [OK]   {name}: {e}")

    # --- C. 功能用例 ---
    print("\n[C] 功能用例（gold = 消化内科 / 胃镜+幽门螺杆菌检测 / 0.75）")
    if info is not None:
        for name, expect, actual in FUNC_CASES:
            try:
                r = run_evaluator(code, "上腹隐痛该去哪个科室", GOLD, actual)
                score = float(r.get("score", -1))
                ok = abs(score - expect) < 1e-9
                print(f"  [{'PASS' if ok else 'FAIL'}] {name}: score={score} 期望={expect}")
                if verbose or not ok:
                    print(f"         reason: {r.get('reason', '')}")
                if not ok:
                    failures.append("功能:" + name)
            except Exception as e:  # noqa: BLE001
                print(f"  [FAIL] {name}: 抛异常 {type(e).__name__}: {e}")
                failures.append("功能异常:" + name)

    # --- D. 参考答案非法 ---
    print("\n[D] 参考答案不是 JSON")
    try:
        r = run_evaluator(code, "q", "not-a-json", "科室：消化内科")
        ok = r.get("score") == 0.0 and "JSON" in str(r.get("reason", ""))
        print(f"  [{'PASS' if ok else 'FAIL'}] score={r.get('score')} reason={r.get('reason')}")
        if not ok:
            failures.append("非法参考答案")
    except Exception as e:  # noqa: BLE001
        print(f"  [FAIL] 抛异常 {type(e).__name__}: {e}")
        failures.append("非法参考答案异常")

    # --- E. 运行时陷阱 ---
    print("\n[E] 运行时陷阱：模块级辅助函数「四闸全过、打分必挂」")
    trap = (
        "def helper(x):\n"
        "    return x.strip()\n"
        "\n"
        "def evaluate(query, expected, actual, runtime_events, **kwargs):\n"
        "    return {'score': 1.0, 'reason': helper(actual)}\n"
    )
    try:
        validate_code_evaluator(trap)
        print("  [OK]   四道闸放行（符合官方行为：闸 3 只跑顶层语句，从不调用 evaluate）")
    except Rejected as e:
        print("  [!!]   四闸竟然拒了，与预期不符:", e)
        failures.append("陷阱四闸行为不符")
    try:
        run_evaluator(trap, "q", "{}", "x")
        print("  [!!]   竟然跑通了，与预期不符")
        failures.append("陷阱未复现")
    except Exception as e:  # noqa: BLE001
        print(f"  [OK]   运行时确实失败: {type(e).__name__}: {e}")
        print("         -> 这就是把 helper 全部写进 evaluate 函数体的理由")

    # --- 结论 ---
    print("\n" + "=" * 72)
    if failures:
        print("RESULT: FAILED")
        for f in failures:
            print("  -", f)
        return 1
    print("RESULT: ALL PASS")
    print("=" * 72)
    print("""
KNOWN_GAPS（复刻与官方实现的差异，必须知道）：
1. 复刻不是官方代码，是同一套规则的照抄；官方在闸 3 之后还有一条 INFO 日志，
   不影响判定结果。
2. 复刻去掉了 sandbox.py _scan_shell_calls 的 pip install 豁免分支
   （allow_package_installs）。评估器场景不会用到，故不实现。
3. 复刻无法验证 Nexent 侧的 DB 落库、版本草稿/发布状态、评分范围校验
   （pass_threshold / 0~100 上限），那部分只能在控制台里验。
4. 真正上线前的最后一验仍是「在控制台创建评估器 → 发布 → 挂到评测任务」，
   本脚本只保证「能通过服务端四道闸 + 逻辑正确」。
""")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
