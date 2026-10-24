"""以 streamable-http 方式连本地 MCP Server，验证 Nexent「远程链接」这条接入路可用。

先起服务：set MCP_TRANSPORT=streamable-http && python mcp-server/server.py
再运行：python tests/test_http_client.py
"""

import asyncio
import json
import os

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

URL = os.environ.get("MEDPAL_MCP_URL", "http://127.0.0.1:8090/mcp")


async def main():
    async with streamablehttp_client(URL) as (r, w, _):
        async with ClientSession(r, w) as s:
            await s.initialize()
            tools = await s.list_tools()
            print("通过 HTTP 拉到工具:", sorted(t.name for t in tools.tools))
            res = await s.call_tool("kg_query", {"seed_entities": ["上腹隐痛"], "max_hops": 2})
            payload = json.loads(res.content[0].text)
            print(
                "kg_query:",
                payload["ok"],
                "路径",
                len(payload["paths"]),
                "版本",
                payload["version"],
            )
            assert payload["ok"] and payload["paths"]
    print("HTTP TRANSPORT OK")


if __name__ == "__main__":
    asyncio.run(main())
