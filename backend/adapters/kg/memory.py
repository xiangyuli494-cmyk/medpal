"""内存图谱仓库：零数据库、零网络，供测试和 W2 演示使用。"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from backend.domain.triage.models import NodeMatch


@dataclass(frozen=True)
class GraphNode:
    key: str
    type: str
    name: str
    aliases: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class GraphEdge:
    src: str
    dst: str
    relation: str


class MemoryGraphRepository:
    """实现 domain.triage.graph.GraphRepository 的内存版本。"""

    def __init__(self, nodes: Iterable[GraphNode], edges: Iterable[GraphEdge]) -> None:
        self._nodes = {node.key: node for node in nodes}
        self._out: dict[tuple[str, str], list[str]] = defaultdict(list)
        self._in: dict[tuple[str, str], list[str]] = defaultdict(list)
        for edge in edges:
            self._out[(edge.src, edge.relation)].append(edge.dst)
            self._in[(edge.dst, edge.relation)].append(edge.src)

    @classmethod
    def from_json(cls, path: str | Path) -> MemoryGraphRepository:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        nodes = [
            GraphNode(
                key=row["key"],
                type=row["type"],
                name=row["name"],
                aliases=tuple(row.get("aliases", ())),
            )
            for row in data["nodes"]
        ]
        edges = [
            GraphEdge(src=row["src"], dst=row["dst"], relation=row["relation"])
            for row in data["edges"]
        ]
        return cls(nodes, edges)

    def node_type(self, node_key: str) -> str | None:
        node = self._nodes.get(node_key)
        return node.type if node else None

    def node_name(self, node_key: str) -> str | None:
        node = self._nodes.get(node_key)
        return node.name if node else None

    def node_exists(self, node_key: str) -> bool:
        return node_key in self._nodes

    def search_nodes(
        self, keyword: str, node_type: str | None = None, limit: int = 12
    ) -> list[NodeMatch]:
        keyword = (keyword or "").strip()
        if not keyword or limit <= 0:
            return []

        found: dict[str, tuple[float, NodeMatch]] = {}

        def add(node: GraphNode, priority: float, match: str) -> None:
            if node_type and node.type != node_type:
                return
            current = found.get(node.key)
            if current is None or priority < current[0]:
                found[node.key] = (
                    priority,
                    NodeMatch(
                        node_key=node.key,
                        node_type=node.type,
                        name=node.name,
                        match=match,
                    ),
                )

        for node in self._nodes.values():
            if keyword in node.aliases:
                add(node, 0, "alias")
            if keyword == node.name:
                add(node, 1, "name_exact")
            if keyword in node.name:
                add(node, 2 + len(node.name) / 100.0, "name_partial")

        ordered = sorted(found.values(), key=lambda item: (item[0], item[1].node_key))
        return [match for _, match in ordered[:limit]]

    def in_neighbors(self, node_key: str, relation: str, limit: int) -> list[str]:
        return self._neighbors(self._in, node_key, relation, limit)

    def out_neighbors(self, node_key: str, relation: str, limit: int) -> list[str]:
        return self._neighbors(self._out, node_key, relation, limit)

    @staticmethod
    def _neighbors(
        index: dict[tuple[str, str], list[str]],
        node_key: str,
        relation: str,
        limit: int,
    ) -> list[str]:
        if limit <= 0:
            return []
        return index.get((node_key, relation), [])[:limit]
