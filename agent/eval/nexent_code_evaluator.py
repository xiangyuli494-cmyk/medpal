def evaluate(query, expected, actual, runtime_events, **kwargs):
    """medpal 决策链回答的 Code 判定器 —— 全部逻辑写在 evaluate 函数体内。

    为什么不能抽模块级辅助函数（实测坑，不是风格偏好）：
      Nexent 执行评估器的方式是
          exec(compile(code, "<evaluator>", "exec"),
               {"__builtins__": ALLOWED_BUILTINS, "json": json},
               local_vars)
          fn = local_vars["evaluate"]
      双字典 exec 下，模块级 def 存进 local_vars，但函数的 __globals__ 指向
      第一个字典，于是 evaluate 里调用模块级 helper 必然
      NameError: name '_xxx' is not defined。
      四道闸全部通过、控制台也能保存，但一跑到打分就抛异常、该评估器一律记
      0 分。所以这里只保留一个顶层 evaluate，helper 用内层 def（闭包可见）。

    判定三件事，加权求总分（0~1）：
      1. 科室是否正确                         权重 0.50
      2. 检查项集合的 Jaccard                 权重 0.30
      3. 完整率已显式给出且不低于参考答案      权重 0.20

    expected 是评测集里的参考答案，JSON 字符串：
      {"department": "消化内科", "exams": ["胃镜"], "trace_completeness": 0.75}
    actual 是智能体最终回答，必须含三行可解析字段：
      科室：消化内科
      检查项：胃镜、幽门螺杆菌检测
      完整率：0.75

    本函数不能查库、读文件、发请求 —— 白名单里没有 open / __import__ /
    subprocess。因此「溯源完整率」只能由 medpal 自己算好写进回答文本，
    这里只做字符串核对。
    """

    STOP_CHARS = ("-", "*", "+")

    def parse_field(text, label):
        # 不能用 re：白名单里没有 re 模块。只能 replace + startswith + 切片。
        for raw in text.splitlines():
            line = raw.replace("**", "").replace("`", "").strip()
            while line[:1] in STOP_CHARS:
                line = line[1:].strip()
            i = 0
            while i < len(line) and line[i].isdigit():
                i += 1
            if i > 0 and line[i:i + 1] in (".", "、", ")", "）"):
                line = line[i + 1:].strip()
            for sep in ("：", ":"):
                head = label + sep
                if line.startswith(head):
                    return line[len(head):].strip()
        return ""

    def split_list(value):
        for sep in ("、", "，", ",", ";", "；", "|"):
            if sep in value:
                parts = value.split(sep)
                return [p.strip() for p in parts if p.strip()]
        return [value.strip()] if value.strip() else []

    def as_float(value, fallback):
        try:
            return float(value)
        except Exception:
            return fallback

    notes = []

    # ---- 参考答案 ----
    try:
        gold = json.loads(expected)  # noqa: F821  json 由沙箱 exec 注入，不能 import
    except Exception:
        return {"score": 0.0, "reason": "参考答案不是合法 JSON，无法判定"}

    gold_dept = str(gold.get("department", "")).strip()
    gold_exams = gold.get("exams", [])
    if not isinstance(gold_exams, list):
        gold_exams = []
    gold_exams = [str(x).strip() for x in gold_exams if str(x).strip()]
    gold_conf = as_float(gold.get("trace_completeness", 0.0), 0.0)

    # ---- 实际回答 ----
    if not actual:
        return {"score": 0.0, "reason": "回答为空"}

    got_dept = parse_field(actual, "科室")
    got_exams = split_list(parse_field(actual, "检查项"))
    got_conf = as_float(parse_field(actual, "完整率"), -1.0)

    # ---- 1. 科室 ----
    dept_score = 0.0
    if got_dept and gold_dept:
        if got_dept == gold_dept:
            dept_score = 1.0
        elif gold_dept in got_dept or got_dept in gold_dept:
            dept_score = 0.5
            notes.append("科室只部分匹配：" + got_dept + " vs " + gold_dept)
    if dept_score == 0.0:
        notes.append("科室不符：期望 " + (gold_dept or "?") + "，实际 " + (got_dept or "缺失"))

    # ---- 2. 检查项 Jaccard ----
    if gold_exams:
        a = set(got_exams)
        b = set(gold_exams)
        union = a | b
        exam_score = (len(a & b) / len(union)) if len(union) > 0 else 0.0
        if exam_score < 1.0:
            notes.append("检查项 Jaccard=" + str(round(exam_score, 3)))
    else:
        exam_score = 1.0 if not got_exams else 0.0

    # ---- 3. 完整率 ----
    conf_score = 0.0
    if got_conf < 0:
        notes.append("回答里没有可解析的「完整率：」字段")
    elif got_conf >= gold_conf:
        conf_score = 1.0
    else:
        notes.append("完整率 " + str(got_conf) + " 低于基准 " + str(gold_conf))

    total = float(round(0.5 * dept_score + 0.3 * exam_score + 0.2 * conf_score, 4))

    if not notes:
        notes.append("科室、检查项、完整率三项均符合")

    return {"score": total, "reason": "；".join(notes)}
