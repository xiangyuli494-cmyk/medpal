"""分诊规则：儿科过滤、置信度阈值与用户可见的理由。"""
from __future__ import annotations

from .models import TriageResult

DEFAULT_MIN_CONFIDENCE = 0.15
DEFAULT_PEDIATRIC_MAX_AGE = 14
DEFAULT_NEIGHBOR_LIMIT = 400

DISCLAIMER = "分诊仅作就诊参考，不能替代医生诊断。"

# 儿科识别不能只匹配「儿」字：
# 「生殖健康与不孕门诊(试管婴儿)」含「儿」，但属于生殖科。
PEDIATRIC_PATTERNS = ("儿科", "小儿", "儿童", "新生儿", "高危儿", "早产儿", "婴幼儿", "少儿")
NOT_PEDIATRIC_PATTERNS = ("试管婴儿", "胎儿", "产前", "孕")


def is_pediatric_department(name: str | None) -> bool:
    """判断科室名是否属于儿科类。"""
    if not name:
        return False
    if any(keyword in name for keyword in NOT_PEDIATRIC_PATTERNS):
        return False
    return any(keyword in name for keyword in PEDIATRIC_PATTERNS)


def reason_text(result: TriageResult, max_evidence: int = 3) -> str:
    """把遍历结果转成一句可读的推荐理由。

    这里只生成「建议前往」，不生成诊断结论；最终展示仍须挂 DISCLAIMER。
    """
    if not result.suggestions:
        return ""

    top = result.suggestions[0]
    evidence = "、".join(top.evidence[:max_evidence])
    text = f"建议前往【{top.department}】就诊"
    if evidence:
        text += f"（依据：{evidence}）"
    if len(result.suggestions) > 1:
        others = "、".join(item.department for item in result.suggestions[1:])
        text += f"。其他可能科室：{others}"
    return text
