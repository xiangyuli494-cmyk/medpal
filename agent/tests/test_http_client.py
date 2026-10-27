"""以 streamable-http 方式连本地 MCP Server，验证 Nexent「远程链接」这条接入路可用。

先起服务：set MCP_TRANSPORT=streamable-http && python mcp-server/server.py
再运行：python tests/test_http_client.py

注意：Windows 上系统代理（注册表 ProxyEnable/ProxyServer）会被 httpx 的 trust_env 读到，
回环地址因此被转发到代理端口，表现为 `502 Bad Gateway`。所以这里显式 trust_env=False，
本机回环永不经过代理。Nexent 容器内连宿主机同理，见 docs/mcp-contract.md §0.2。
"""

import asyncio
import json
import os

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

URL = os.environ.get("MEDPAL_MCP_URL", "http://127.0.0.1:8090/mcp")


def _no_proxy_client(
    headers: dict | None = None,
    timeout: httpx.Timeout | None = None,
    auth: httpx.Auth | None = None,
) -> httpx.AsyncClient:
    """回环直连，不读系统代理。"""
    kwargs = {
        "headers": headers,
        "auth": auth,
        "follow_redirects": True,
        "trust_env": False,
    }
    if timeout is not None:
        kwargs["timeout"] = timeout
    return httpx.AsyncClient(**kwargs)


async def main():
    async with streamablehttp_client(URL, httpx_client_factory=_no_proxy_client) as (r, w, _):
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
