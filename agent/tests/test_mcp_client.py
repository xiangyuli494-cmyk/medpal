"""用官方 MCP 客户端以 stdio 方式连上 server.py，验证工具清单与一次真实调用。

运行：python tests/test_mcp_client.py
"""
import asyncio, json, os, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SERVER = ROOT / "mcp-server" / "server.py"
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

EXPECTED = [
    "ingest_asset", "get_asset_card", "kg_query", "onto_propose", "onto_commit",
    "std_align", "trace_write", "skill_export", "kb_search", "health",
]


async def main():
    params = StdioServerParameters(
        command=sys.executable, args=[str(SERVER)],
        env={**os.environ, "MCP_TRANSPORT": "stdio"},
    )
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            tools = await s.list_tools()
            names = sorted(t.name for t in tools.tools)
            print("tools:", names)
            missing = [n for n in EXPECTED if n not in names]
            assert not missing, f"缺少工具: {missing}"

            res = await s.call_tool("health", {})  # 元数据冒烟：库能开、版本指针可读
            payload = json.loads(res.content[0].text)
            print("health:", payload)
            assert payload["ok"] and payload["triples"] >= 12, payload

            res = await s.call_tool("kg_query", {"seed_entities": ["上腹隐痛"], "max_hops": 2})
            payload = json.loads(res.content[0].text)
            ids = {n for p in payload.get("paths", []) for n in p["nodes"]}
            print("kg_query 路径数:", len(payload.get("paths", [])), "命中 K27:", "K27" in ids)
            assert payload["ok"] and "K27" in ids

            res = await s.call_tool("std_align", {"entity_text": "上腹部痛"})
            payload = json.loads(res.content[0].text)
            print("std_align:", payload.get("scheme"), payload.get("code"), payload.get("match"))
            assert payload.get("ok") and payload.get("code") == "R10.1" and payload.get("scheme") == "ICD-10"
    print("MCP CLIENT OK")


if __name__ == "__main__":
    asyncio.run(main())
