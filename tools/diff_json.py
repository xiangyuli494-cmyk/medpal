"""黄金文件比对：骨架是不是还连着电。

    python tools/diff_json.py tmp/trace.json fixtures/golden_trace.json

只比业务字段，忽略易变字段。有差异就打印前 20 处并以退出码 1 结束——
CI 红灯就是从这里亮起的。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

IGNORE = {"generated_at", "duration_ms", "db_path", "timestamp", "host", "elapsed"}


def strip(obj):
    if isinstance(obj, dict):
        return {k: strip(v) for k, v in obj.items() if k not in IGNORE}
    if isinstance(obj, list):
        return [strip(v) for v in obj]
    return obj


def walk(a, b, path, out):
    if len(out) >= 20:
        return
    if type(a) is not type(b):
        out.append(path + ": 类型不同 " + type(a).__name__ + " vs " + type(b).__name__)
        return
    if isinstance(a, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a:
                out.append(path + "." + k + ": 黄金里有、结果里没有")
            elif k not in b:
                out.append(path + "." + k + ": 结果里多出 " + k)
            else:
                walk(a[k], b[k], path + "." + k, out)
    elif isinstance(a, list):
        if len(a) != len(b):
            out.append(path + ": 长度 " + str(len(a)) + " vs " + str(len(b)))
        for i in range(min(len(a), len(b))):
            walk(a[i], b[i], path + "[" + str(i) + "]", out)
    elif a != b:
        out.append(path + ": " + json.dumps(a, ensure_ascii=False)
                   + " vs " + json.dumps(b, ensure_ascii=False))


def main() -> int:
    if len(sys.argv) != 3:
        print("用法: python tools/diff_json.py <实际> <黄金>")
        return 2
    actual = strip(json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")))
    golden = strip(json.loads(Path(sys.argv[2]).read_text(encoding="utf-8")))

    diffs = []
    walk(actual, golden, "$", diffs)
    if diffs:
        print("骨架断了 " + str(len(diffs)) + " 处：")
        for d in diffs:
            print("  - " + d)
        return 1
    print("骨架通电：与黄金文件一致")
    return 0


if __name__ == "__main__":
    sys.exit(main())
