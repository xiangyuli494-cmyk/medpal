"""纯图遍历：症状 / 疾病 / 科室 -> 候选科室。

算法来自毕设 KG 的 recommend.py，但去掉了所有 SQL：
数据访问通过 GraphRepository 注入，domain 不碰数据库。

关键行为（与旧实现保持一致）：
1. 症状起点：症状 <-表现为- 疾病 -> 就诊于 -> 科室；
2. 疾病起点：只走直接边，不做症状扩散；
3. 科室起点：自己计一票；
4. 儿科过滤：只有明确年龄 < 阈值才保留儿科；年龄未知按成人处理；
5. confidence 是相对占比，不是准确率。
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable

from .graph import GraphRepository
from .models import DepartmentSuggestion, TriageResult
from .rules import (
    DEFAULT_MIN_CONFIDENCE,
    DEFAULT_NEIGHBOR_LIMIT,
    DEFAULT_PEDIATRIC_MAX_AGE,
    is_pediatric_department,
)

SYMPTOM_RELATION = "表现为"
DEPARTMENT_RELATION = "就诊于"
MAX_EVIDENCE = 6
MAX_FILTERED_PEDIATRIC = 8


def traverse(
    node_keys: Iterable[str] | None,
    repo: GraphRepository,
    *,
    top_n: int = 3,
    min_confidence: float | None = None,
    age: int | None = None,
    pediatric_max_age: int = DEFAULT_PEDIATRIC_MAX_AGE,
    neighbor_limit: int = DEFAULT_NEIGHBOR_LIMIT,
) -> TriageResult:
    """从一组起点节点遍历到候选科室，并按票数排序。"""
    keys = [key for key in (node_keys or []) if key]
    if not keys:
        return TriageResult()

    keep_pediatric = age is not None and age < pediatric_max_age
    scores: Counter[str] = Counter()
    evidence: dict[str, list[str]] = defaultdict(list)
    seen_diseases: set[str] = set()
    skipped_pediatric: set[str] = set()

    def add_departments(disease_key: str) -> None:
        if disease_key in seen_diseases:
            return
        seen_diseases.add(disease_key)

        for department_key in repo.out_neighbors(disease_key, DEPARTMENT_RELATION, neighbor_limit):
            department = repo.node_name(department_key)
            if not keep_pediatric and department and is_pediatric_department(department):
                skipped_pediatric.add(department)
                continue
            scores[department_key] += 1
            if len(evidence[department_key]) < MAX_EVIDENCE:
                evidence[department_key].append(disease_key)

    for node_key in keys:
        node_type = repo.node_type(node_key)
        if node_type == "symptom":
            for disease_key in repo.in_neighbors(node_key, SYMPTOM_RELATION, neighbor_limit):
                add_departments(disease_key)
        elif node_type == "disease":
            add_departments(node_key)
        elif node_type == "department":
            scores[node_key] += 1
            if len(evidence[node_key]) < MAX_EVIDENCE:
                evidence[node_key].append(node_key)

    total_votes = sum(scores.values())
    if total_votes == 0:
        return TriageResult()

    threshold = DEFAULT_MIN_CONFIDENCE if min_confidence is None else min_confidence
    ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))[: max(1, top_n)]

    suggestions = tuple(
        DepartmentSuggestion(
            department=repo.node_name(department_key) or department_key,
            department_key=department_key,
            votes=votes,
            confidence=round(votes / total_votes, 4),
            evidence=tuple(repo.node_name(key) or key for key in evidence[department_key]),
        )
        for department_key, votes in ranked
    )

    top_confidence = suggestions[0].confidence
    return TriageResult(
        suggestions=suggestions,
        total_votes=total_votes,
        confidence=top_confidence,
        enough=top_confidence >= threshold,
        filtered_pediatric=tuple(sorted(skipped_pediatric)[:MAX_FILTERED_PEDIATRIC]),
    )
