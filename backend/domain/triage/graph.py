"""只读图谱访问端口。

domain 只依赖这个 Protocol；MySQL / 内存图 / 测试假图都实现它。
"""
from __future__ import annotations

from typing import Protocol

from .models import NodeMatch


class GraphRepository(Protocol):
    """图谱查询的最小接口。"""

    def node_type(self, node_key: str) -> str | None:
        """返回节点类型；节点不存在时返回 None。"""

    def node_name(self, node_key: str) -> str | None:
        """返回节点展示名；节点不存在时返回 None。"""

    def node_exists(self, node_key: str) -> bool:
        """判断节点是否存在，用于校验 LLM 编造的 key。"""

    def search_nodes(
        self, keyword: str, node_type: str | None, limit: int
    ) -> list[NodeMatch]:
        """按关键词检索候选节点；供规则层与 LLM 工具使用。"""

    def in_neighbors(self, node_key: str, relation: str, limit: int) -> list[str]:
        """返回以 node_key 为终点的邻居（边方向：邻居 -> node_key）。"""

    def out_neighbors(self, node_key: str, relation: str, limit: int) -> list[str]:
        """返回以 node_key 为起点的邻居（边方向：node_key -> 邻居）。"""
