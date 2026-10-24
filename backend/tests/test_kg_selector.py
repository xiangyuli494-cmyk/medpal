"""KG 节点选择器测试：规则层 + FakeLlm，不联网。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.adapters.kg.memory import MemoryGraphRepository
from backend.adapters.kg.selector import NodeSelector, load_prompt
from backend.adapters.llm.fakes import FakeLlm
from backend.domain.triage import traverse


@pytest.fixture()
def repo(repo_root: Path) -> MemoryGraphRepository:
    return MemoryGraphRepository.from_json(repo_root / "fixtures" / "kg" / "demo_graph.json")


def _tool_call(name: str, arguments: dict, call_id: str = "call_1") -> dict:
    return {
        "id": call_id,
        "type": "function",
        "function": {
            "name": name,
            "arguments": json.dumps(arguments, ensure_ascii=False),
        },
    }


def _message(*calls: dict, content: str | None = None) -> dict:
    return {"role": "assistant", "content": content, "tool_calls": list(calls)}


def test_rule_layer_alias(repo: MemoryGraphRepository) -> None:
    result = NodeSelector(repo, prompt="test").select("腿痛", use_llm=False)

    assert result.source == "rule"
    assert result.nodes == ("symptom:腿疼",)


def test_rule_layer_exact_name(repo: MemoryGraphRepository) -> None:
    result = NodeSelector(repo, prompt="test").select("腿疼", use_llm=False)

    assert result.source == "rule"
    assert result.nodes == ("symptom:腿疼",)


def test_rule_layer_does_not_use_partial_match(repo: MemoryGraphRepository) -> None:
    result = NodeSelector(repo, prompt="test").select("腿", use_llm=False)

    assert result.source == "none"
    assert result.nodes == ()


def test_no_rule_without_llm(repo: MemoryGraphRepository) -> None:
    result = NodeSelector(repo, prompt="test").select("我腿疼", use_llm=False)

    assert result.source == "none"
    assert "跳过 LLM" in result.note


def test_empty_text(repo: MemoryGraphRepository) -> None:
    result = NodeSelector(repo, prompt="test").select("")

    assert result.source == "none"
    assert result.note == "输入为空"
    assert result.elapsed_ms == 0


def test_default_prompt_loads(repo: MemoryGraphRepository) -> None:
    selector = NodeSelector(repo)

    assert "search_nodes" in selector.prompt
    assert "select_nodes" in selector.prompt


def test_load_prompt_rejects_empty_file(tmp_path: Path) -> None:
    path = tmp_path / "prompt.md"
    path.write_text("", encoding="utf-8")

    with pytest.raises(ValueError):
        load_prompt(path)


def test_llm_selects_valid_nodes_and_filters_invalid(repo: MemoryGraphRepository) -> None:
    llm = FakeLlm(
        [
            _message(
                _tool_call(
                    "select_nodes",
                    {"node_keys": ["symptom:腿疼", "symptom:fake"]},
                )
            )
        ]
    )

    result = NodeSelector(repo, llm, prompt="test").select("我腿疼")

    assert result.source == "llm"
    assert result.nodes == ("symptom:腿疼",)
    assert result.trace[0]["invalid"] == ["symptom:fake"]


def test_llm_search_then_select(repo: MemoryGraphRepository) -> None:
    llm = FakeLlm(
        [
            _message(_tool_call("search_nodes", {"keyword": "腿疼"})),
            _message(_tool_call("select_nodes", {"node_keys": ["symptom:腿疼"]})),
        ]
    )

    result = NodeSelector(repo, llm, prompt="test").select("我腿疼")

    assert result.source == "llm"
    assert result.nodes == ("symptom:腿疼",)
    assert any(message["role"] == "tool" for message in llm.calls[1]["messages"])


def test_llm_search_with_empty_keyword(repo: MemoryGraphRepository) -> None:
    llm = FakeLlm(
        [
            _message(_tool_call("search_nodes", {"keyword": ""})),
            _message(_tool_call("select_nodes", {"node_keys": []})),
        ]
    )

    result = NodeSelector(repo, llm, prompt="test").select("我腿疼")

    assert result.source == "none"
    assert "未匹配到节点" in result.note
    assert "关键词为空" in result.trace[0]["result_brief"]


def test_llm_unknown_tool_then_select(repo: MemoryGraphRepository) -> None:
    llm = FakeLlm(
        [
            _message(_tool_call("unknown_tool", {})),
            _message(_tool_call("select_nodes", {"node_keys": ["symptom:腿疼"]})),
        ]
    )

    result = NodeSelector(repo, llm, prompt="test").select("我腿疼")

    assert result.source == "llm"
    assert any(item.get("error") for item in result.trace)


def test_llm_no_tool_calls(repo: MemoryGraphRepository) -> None:
    llm = FakeLlm([{"role": "assistant", "content": "我想想"}])

    result = NodeSelector(repo, llm, prompt="test").select("我腿疼")

    assert result.source == "none"
    assert "未按要求" in result.note


def test_llm_max_rounds(repo: MemoryGraphRepository) -> None:
    llm = FakeLlm(
        [
            _message(_tool_call("search_nodes", {"keyword": "腿疼"})),
            _message(_tool_call("search_nodes", {"keyword": "腿疼"})),
        ]
    )

    result = NodeSelector(repo, llm, prompt="test", max_rounds=2).select("我腿疼")

    assert result.source == "none"
    assert "超过 2 轮" in result.note


def test_llm_error(repo: MemoryGraphRepository) -> None:
    llm = FakeLlm([])

    result = NodeSelector(repo, llm, prompt="test").select("我腿疼")

    assert result.source == "none"
    assert "LLM 调用失败" in result.note


def test_select_nodes_accepts_json_string(repo: MemoryGraphRepository) -> None:
    llm = FakeLlm(
        [
            _message(
                _tool_call(
                    "select_nodes",
                    {"node_keys": '["symptom:腿疼"]'},
                )
            )
        ]
    )

    result = NodeSelector(repo, llm, prompt="test").select("我腿疼")

    assert result.source == "llm"
    assert result.nodes == ("symptom:腿疼",)


def test_selector_feeds_traversal(repo: MemoryGraphRepository) -> None:
    llm = FakeLlm([_message(_tool_call("select_nodes", {"node_keys": ["symptom:腿疼"]}))])

    selection = NodeSelector(repo, llm, prompt="test").select("我腿疼")
    result = traverse(selection.nodes, repo)

    assert selection.source == "llm"
    assert result.suggestions[0].department == "骨科专科"


def test_memory_repository_search(repo: MemoryGraphRepository) -> None:
    assert repo.search_nodes("腿痛", None, 5)[0].node_key == "symptom:腿疼"
    assert repo.search_nodes("腿疼", None, 5)[0].match == "name_exact"
    assert [match.node_key for match in repo.search_nodes("腿", None, 5)] == [
        "symptom:腿疼",
        "disease:腰腿痛",
    ]
    assert repo.search_nodes("腿疼", "disease", 5) == []
    assert repo.search_nodes("", None, 5) == []
    assert repo.search_nodes("腿疼", None, 0) == []
    assert repo.node_exists("symptom:腿疼") is True
    assert repo.node_exists("missing") is False
