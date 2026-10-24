"""KG 节点选择器：规则层 -> LLM 工具调用层 -> 图谱校验。

LLM 只能「选」节点，不能「造」节点：
LLM 提议的每个 node_key 都必须经过 GraphRepository 校验，编造的 key 一律丢弃。
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

from backend.adapters.llm.base import LlmClient, LlmError
from backend.domain.triage.graph import GraphRepository

MAX_ROUNDS = 6
MAX_SEARCH = 12
MAX_NODES = 5
RULE_MATCH_TYPES = ("alias", "name_exact")

PROMPT_PATH = Path(__file__).with_name("prompts") / "select_nodes.md"

SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "search_nodes",
        "description": (
            "在医学知识图谱里按关键词查找节点。"
            "支持口语表达，也支持直接传整句；工具会返回节点名、类型与匹配方式。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "keyword": {
                    "type": "string",
                    "description": "要查找的关键词，可直接传患者的原话",
                },
                "node_type": {
                    "type": "string",
                    "enum": ["symptom", "disease", "department"],
                    "description": "限定节点类型，不填则搜全部",
                },
            },
            "required": ["keyword"],
        },
    },
}

SELECT_TOOL = {
    "type": "function",
    "function": {
        "name": "select_nodes",
        "description": (
            "当你确定了与患者描述最相关的图谱节点后，调用本工具提交结果。"
            "只能选择 search_nodes 真实返回过的节点；找不到就提交空数组。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "node_keys": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": '选中的节点键列表，如 ["symptom:腿疼"]，最多 5 个',
                },
                "reason": {"type": "string", "description": "简要说明为什么选这些节点"},
            },
            "required": ["node_keys"],
        },
    },
}


@dataclass(frozen=True)
class SelectionResult:
    """节点选择结果。source 取值：rule / llm / none。"""

    nodes: tuple[str, ...]
    source: str
    trace: tuple[dict, ...] = ()
    note: str = ""
    elapsed_ms: int = 0


def load_prompt(path: str | Path | None = None) -> str:
    """读取 system prompt；文件不存在时直接报错，避免静默用错提示词。"""
    prompt_path = Path(path) if path is not None else PROMPT_PATH
    text = prompt_path.read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError(f"提示词文件为空：{prompt_path}")
    return text


class NodeSelector:
    """把患者文本转换成通过图谱校验的节点。"""

    def __init__(
        self,
        repo: GraphRepository,
        llm: LlmClient | None = None,
        prompt: str | None = None,
        max_rounds: int = MAX_ROUNDS,
    ) -> None:
        self.repo = repo
        self.llm = llm
        self.prompt = load_prompt() if prompt is None else prompt
        self.max_rounds = max_rounds

    def select(self, text: str, use_llm: bool = True) -> SelectionResult:
        started = time.monotonic()
        text = (text or "").strip()
        if not text:
            return SelectionResult((), "none", note="输入为空", elapsed_ms=0)

        rule_keys = self._rule_match(text)
        if rule_keys:
            trace = ({"stage": "rule", "hit": rule_keys},)
            return SelectionResult(
                tuple(rule_keys),
                "rule",
                trace,
                elapsed_ms=self._elapsed_ms(started),
            )

        if use_llm and self.llm is not None:
            keys, trace, note = self._llm_select(text)
            if keys:
                return SelectionResult(
                    tuple(keys),
                    "llm",
                    tuple(trace),
                    elapsed_ms=self._elapsed_ms(started),
                )
            return SelectionResult(
                (),
                "none",
                tuple(trace),
                note or "规则层与 LLM 层都未匹配到节点",
                self._elapsed_ms(started),
            )

        note = "调用方要求跳过 LLM" if not use_llm else "未配置 LLM"
        return SelectionResult((), "none", note=note, elapsed_ms=self._elapsed_ms(started))

    def _rule_match(self, text: str) -> list[str]:
        keys: list[str] = []
        for match in self.repo.search_nodes(text, None, MAX_SEARCH):
            if match.match in RULE_MATCH_TYPES and match.node_key not in keys:
                keys.append(match.node_key)
            if len(keys) >= MAX_NODES:
                break
        return keys

    def _llm_select(self, text: str) -> tuple[list[str], list[dict], str]:
        assert self.llm is not None
        trace: list[dict] = []
        messages = [
            {"role": "system", "content": self.prompt},
            {"role": "user", "content": f"患者主诉：{text}"},
        ]
        tools = [SEARCH_TOOL, SELECT_TOOL]

        for round_no in range(1, self.max_rounds + 1):
            try:
                message = self.llm.chat(messages, tools)
            except LlmError as exc:
                trace.append({"round": round_no, "note": f"LLM 调用失败: {exc}"})
                return [], trace, f"LLM 调用失败: {exc}"

            tool_calls = message.get("tool_calls") or []
            if not isinstance(tool_calls, list):
                tool_calls = []
            if not tool_calls:
                trace.append({"round": round_no, "note": "LLM 未调用工具"})
                return [], trace, "LLM 未按要求调用工具"

            messages.append(
                {
                    "role": "assistant",
                    "content": message.get("content"),
                    "tool_calls": tool_calls,
                }
            )

            for call in tool_calls:
                if not isinstance(call, dict):
                    continue
                name, args = self._parse_call(call)
                call_id = str(call.get("id") or "")

                if name == "select_nodes":
                    keys = self._node_keys(args)
                    valid, invalid = self._validate_keys(keys)
                    trace.append(
                        {
                            "round": round_no,
                            "tool": "select_nodes",
                            "submitted": keys,
                            "valid": valid,
                            "invalid": invalid,
                            "reason": str(args.get("reason") or "")[:120],
                        }
                    )
                    return valid[:MAX_NODES], trace, ""

                if name == "search_nodes":
                    keyword = str(args.get("keyword") or "")
                    result = self._search(keyword, args.get("node_type"))
                    trace.append(
                        {
                            "round": round_no,
                            "tool": "search_nodes",
                            "args": args,
                            "result_brief": self._brief_result(result),
                        }
                    )
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call_id,
                            "content": json.dumps(result, ensure_ascii=False)[:4000],
                        }
                    )
                    continue

                error = {"error": f"未知工具: {name}"}
                trace.append({"round": round_no, "tool": name, "error": error["error"]})
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call_id,
                        "content": json.dumps(error, ensure_ascii=False),
                    }
                )

        note = f"超过 {self.max_rounds} 轮工具调用仍未提交结果"
        return [], trace, note

    def _search(self, keyword: str, node_type: object = None) -> dict:
        keyword = keyword.strip()
        if not keyword:
            return {"keyword": "", "count": 0, "nodes": [], "error": "关键词为空"}

        type_filter = node_type if isinstance(node_type, str) and node_type else None
        matches = self.repo.search_nodes(keyword, type_filter, MAX_SEARCH)
        nodes = [
            {
                "node_key": match.node_key,
                "type": match.node_type,
                "name": match.name,
                "match": match.match,
            }
            for match in matches
        ]
        result: dict = {"keyword": keyword, "count": len(nodes), "nodes": nodes}
        if not nodes:
            result["hint"] = (
                "没有找到匹配节点。请改用更短、更常见的医学词重试；"
                "如果确实没有相关概念，请调用 select_nodes 提交空数组。"
            )
        return result

    def _validate_keys(self, keys: list[str]) -> tuple[list[str], list[str]]:
        valid: list[str] = []
        invalid: list[str] = []
        for key in keys:
            if key in valid or key in invalid:
                continue
            (valid if self.repo.node_exists(key) else invalid).append(key)
        return valid, invalid

    @staticmethod
    def _node_keys(args: dict) -> list[str]:
        raw = args.get("node_keys") or []
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except json.JSONDecodeError:
                raw = [raw]
        if not isinstance(raw, list):
            return []
        return [str(key) for key in raw if key]

    @staticmethod
    def _parse_call(call: dict) -> tuple[str, dict]:
        function = call.get("function")
        if not isinstance(function, dict):
            return "", {}
        name = str(function.get("name") or "")
        raw_args = function.get("arguments")
        if isinstance(raw_args, dict):
            return name, raw_args
        if not isinstance(raw_args, str) or not raw_args.strip():
            return name, {}
        try:
            args = json.loads(raw_args)
        except json.JSONDecodeError:
            return name, {}
        return name, args if isinstance(args, dict) else {}

    @staticmethod
    def _brief_result(result: dict) -> str:
        if "error" in result:
            return f"错误: {result['error']}"
        names = [node["name"] for node in result.get("nodes", [])[:5]]
        return f"找到 {result.get('count', 0)} 个: {names}"

    @staticmethod
    def _elapsed_ms(started: float) -> int:
        return int((time.monotonic() - started) * 1000)
