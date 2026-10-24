"""纯数据结构：分诊遍历的输入与输出。

这一层不依赖数据库、网络或任何框架，便于 100% 单元测试。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DepartmentSuggestion:
    """一个候选科室及其投票结果。"""

    department: str
    department_key: str
    votes: int
    confidence: float
    evidence: tuple[str, ...] = ()


@dataclass(frozen=True)
class NodeMatch:
    """图谱检索命中的一个节点。"""

    node_key: str
    node_type: str
    name: str
    match: str


@dataclass(frozen=True)
class TriageResult:
    """一次分诊遍历的完整结果。

    confidence 是「相对占比」，不是准确率；UI 不得把它标成「准确率」。
    """

    suggestions: tuple[DepartmentSuggestion, ...] = ()
    total_votes: int = 0
    confidence: float = 0.0
    enough: bool = False
    filtered_pediatric: tuple[str, ...] = ()
