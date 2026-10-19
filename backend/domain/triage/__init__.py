"""纯分诊逻辑（C2 可选能力）。

只做「文本节点 -> 候选科室」的图遍历；
文本抽取、LLM 选节点和数据库访问都在 adapters 层。
"""
from .graph import GraphRepository
from .models import DepartmentSuggestion, NodeMatch, TriageResult
from .rules import (
    DEFAULT_MIN_CONFIDENCE,
    DEFAULT_NEIGHBOR_LIMIT,
    DEFAULT_PEDIATRIC_MAX_AGE,
    DISCLAIMER,
    is_pediatric_department,
    reason_text,
)
from .traverse import traverse

__all__ = [
    "DEFAULT_MIN_CONFIDENCE",
    "DEFAULT_NEIGHBOR_LIMIT",
    "DEFAULT_PEDIATRIC_MAX_AGE",
    "DISCLAIMER",
    "DepartmentSuggestion",
    "GraphRepository",
    "NodeMatch",
    "TriageResult",
    "is_pediatric_department",
    "reason_text",
    "traverse",
]
