"""不启动网络服务，直接观察 FastMCP 注册的协议对象。"""

import asyncio

from mcp_lab.server import AUTH_GATEWAY, mcp
from mcp_lab.host import LocalFastMCPTransport, SafeMCPHost
from mcp_lab.models import Principal


async def async_main() -> None:
    tools = await mcp.list_tools()
    resources = await mcp.list_resources()
    templates = await mcp.list_resource_templates()
    principal = Principal(
        actor_id="demo-user",
        tenant="tenant-a",
        scopes=frozenset({"metrics:read", "schema:read", "query:execute"}),
    )
    host = SafeMCPHost(
        LocalFastMCPTransport(mcp),
        principal,
        # 本地 demo 由同进程网关签发；真实部署应由 HTTP/身份网关完成认证后注入。
        auth_context=AUTH_GATEWAY.issue(principal),
    )
    catalog = await host.discover()
    result = await host.call_tool(
        "run_readonly_sql",
        {
            "sql": "SELECT day, revenue FROM analytics.daily_metrics ORDER BY day DESC",
            "max_rows": 10,
        },
        request_id="demo-001",
    )
    print("tools:", [tool.name for tool in tools])
    print("resources:", [str(resource.uri) for resource in resources])
    print("templates:", [template.uriTemplate for template in templates])
    print("capability fingerprint:", catalog.fingerprint)
    print("tool result:", result.model_dump())


def main() -> None:
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
