"""纯分诊算法测试：不联网、不读 MySQL、不调 LLM。"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.adapters.kg.memory import GraphEdge, GraphNode, MemoryGraphRepository
from backend.domain.triage import (
    TriageResult,
    is_pediatric_department,
    reason_text,
    traverse,
)
from backend.domain.triage.models import DepartmentSuggestion


@pytest.fixture()
def repo(repo_root: Path) -> MemoryGraphRepository:
    return MemoryGraphRepository.from_json(repo_root / "fixtures" / "kg" / "demo_graph.json")


def _repo(nodes: list[GraphNode], edges: list[GraphEdge]) -> MemoryGraphRepository:
    return MemoryGraphRepository(nodes, edges)


def test_empty_input_returns_empty(repo: MemoryGraphRepository) -> None:
    assert traverse(None, repo) == TriageResult()
    assert traverse([], repo) == TriageResult()


def test_symptom_to_departments(repo: MemoryGraphRepository) -> None:
    result = traverse(["symptom:腿疼"], repo)

    assert result.total_votes == 3
    assert result.confidence == 0.6667
    assert result.enough is True
    assert [item.department for item in result.suggestions] == ["骨科专科", "风湿免疫科"]

    top = result.suggestions[0]
    assert top.department_key == "department:骨科专科"
    assert top.votes == 2
    assert set(top.evidence) == {"腰腿痛", "关节退行性变"}
    assert result.filtered_pediatric == ()


def test_disease_start_only_uses_direct_edges(repo: MemoryGraphRepository) -> None:
    result = traverse(["disease:腰腿痛"], repo)

    assert result.total_votes == 1
    assert len(result.suggestions) == 1
    assert result.suggestions[0].department == "骨科专科"


def test_department_start_counts_itself(repo: MemoryGraphRepository) -> None:
    result = traverse(["department:骨科专科"], repo)

    assert result.total_votes == 1
    assert result.suggestions[0].evidence == ("骨科专科",)


@pytest.mark.parametrize("age", [None, 30])
def test_pediatric_filtered_for_adult_or_unknown(
    repo: MemoryGraphRepository, age: int | None
) -> None:
    result = traverse(["symptom:上不来气"], repo, age=age)

    assert [item.department for item in result.suggestions] == ["呼吸内科"]
    assert result.filtered_pediatric == ("儿科内科",)


def test_pediatric_kept_for_child(repo: MemoryGraphRepository) -> None:
    result = traverse(["symptom:上不来气"], repo, age=13)

    assert {item.department for item in result.suggestions} == {"呼吸内科", "儿科内科"}
    assert result.total_votes == 2
    assert result.filtered_pediatric == ()


def test_pediatric_age_boundary(repo: MemoryGraphRepository) -> None:
    assert traverse(["symptom:上不来气"], repo, age=13).total_votes == 2
    assert traverse(["symptom:上不来气"], repo, age=14).total_votes == 1


def test_not_pediatric_pattern_wins(repo: MemoryGraphRepository) -> None:
    result = traverse(["symptom:怀不上"], repo, age=30)

    assert [item.department for item in result.suggestions] == ["生殖健康与不孕门诊(试管婴儿)"]
    assert result.filtered_pediatric == ()


def test_missing_node_ignored(repo: MemoryGraphRepository) -> None:
    assert traverse(["symptom:不存在"], repo) == TriageResult()


def test_symptom_without_diseases(repo: MemoryGraphRepository) -> None:
    assert traverse(["symptom:头晕"], repo) == TriageResult()


def test_confidence_threshold(repo: MemoryGraphRepository) -> None:
    assert traverse(["symptom:腿疼"], repo, min_confidence=0.9).enough is False
    assert traverse(["symptom:腿疼"], repo, min_confidence=0.1).enough is True
    assert traverse(["symptom:腿疼"], repo).enough is True


def test_top_n(repo: MemoryGraphRepository) -> None:
    result = traverse(["symptom:腿疼"], repo, top_n=1)

    assert len(result.suggestions) == 1
    assert result.total_votes == 3
    assert result.confidence == 0.6667
    assert len(traverse(["symptom:腿疼"], repo, top_n=0).suggestions) == 1


def test_reason_text(repo: MemoryGraphRepository) -> None:
    result = traverse(["symptom:腿疼"], repo)
    text = reason_text(result)

    assert text.startswith("建议前往【骨科专科】就诊")
    assert "依据：" in text
    assert "其他可能科室：风湿免疫科" in text
    assert reason_text(TriageResult()) == ""


def test_reason_text_without_evidence() -> None:
    result = TriageResult(
        suggestions=(DepartmentSuggestion("骨科", "department:骨科", 1, 1.0),),
        total_votes=1,
        confidence=1.0,
        enough=True,
    )

    assert reason_text(result) == "建议前往【骨科】就诊"


def test_is_pediatric_department() -> None:
    assert is_pediatric_department("儿科内科") is True
    assert is_pediatric_department("小儿外科专科") is True
    assert is_pediatric_department("生殖健康与不孕门诊(试管婴儿)") is False
    assert is_pediatric_department("产科专科") is False
    assert is_pediatric_department(None) is False
    assert is_pediatric_department("") is False


def test_memory_repository_queries(repo: MemoryGraphRepository) -> None:
    assert repo.node_type("symptom:腿疼") == "symptom"
    assert repo.node_name("department:骨科专科") == "骨科专科"
    assert repo.node_type("missing") is None
    assert repo.node_name("missing") is None
    assert repo.in_neighbors("symptom:腿疼", "表现为", 10) == [
        "disease:腰腿痛",
        "disease:关节退行性变",
        "disease:风湿性关节炎",
    ]
    assert repo.out_neighbors("disease:腰腿痛", "就诊于", 10) == ["department:骨科专科"]
    assert repo.in_neighbors("symptom:腿疼", "other", 10) == []
    assert repo.out_neighbors("disease:腰腿痛", "就诊于", 0) == []


def test_evidence_capped_at_six() -> None:
    nodes = [
        GraphNode("symptom:s", "symptom", "症状"),
        GraphNode("department:d", "department", "科室"),
    ]
    edges: list[GraphEdge] = []
    for index in range(7):
        disease = f"disease:d{index}"
        nodes.append(GraphNode(disease, "disease", f"疾病{index}"))
        edges.append(GraphEdge(disease, "symptom:s", "表现为"))
        edges.append(GraphEdge(disease, "department:d", "就诊于"))

    result = traverse(["symptom:s"], _repo(nodes, edges))

    assert result.total_votes == 7
    assert len(result.suggestions[0].evidence) == 6


def test_same_disease_not_counted_twice() -> None:
    nodes = [
        GraphNode("symptom:a", "symptom", "A"),
        GraphNode("symptom:b", "symptom", "B"),
        GraphNode("disease:x", "disease", "X"),
        GraphNode("department:d", "department", "D"),
    ]
    edges = [
        GraphEdge("disease:x", "symptom:a", "表现为"),
        GraphEdge("disease:x", "symptom:b", "表现为"),
        GraphEdge("disease:x", "department:d", "就诊于"),
    ]

    result = traverse(["symptom:a", "symptom:b"], _repo(nodes, edges))

    assert result.total_votes == 1


def test_neighbor_limit() -> None:
    nodes = [
        GraphNode("symptom:s", "symptom", "S"),
        GraphNode("disease:a", "disease", "A"),
        GraphNode("disease:b", "disease", "B"),
        GraphNode("department:d1", "department", "D1"),
        GraphNode("department:d2", "department", "D2"),
    ]
    edges = [
        GraphEdge("disease:a", "symptom:s", "表现为"),
        GraphEdge("disease:b", "symptom:s", "表现为"),
        GraphEdge("disease:a", "department:d1", "就诊于"),
        GraphEdge("disease:b", "department:d2", "就诊于"),
    ]

    result = traverse(["symptom:s"], _repo(nodes, edges), neighbor_limit=1)

    assert result.total_votes == 1
    assert len(result.suggestions) == 1


def test_missing_department_name_falls_back_to_key() -> None:
    nodes = [
        GraphNode("symptom:s", "symptom", "S"),
        GraphNode("disease:x", "disease", "X"),
    ]
    edges = [
        GraphEdge("disease:x", "symptom:s", "表现为"),
        GraphEdge("disease:x", "department:missing", "就诊于"),
    ]

    result = traverse(["symptom:s"], _repo(nodes, edges))

    assert result.suggestions[0].department == "department:missing"
    assert result.suggestions[0].evidence == ("X",)


def test_unknown_node_type_ignored() -> None:
    repository = _repo([GraphNode("drug:x", "drug", "药")], [])

    assert traverse(["drug:x"], repository) == TriageResult()
