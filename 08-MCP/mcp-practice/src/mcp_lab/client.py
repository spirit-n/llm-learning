"""使用官方 ClientSession 测试 stdio 与 Streamable HTTP。"""

import argparse
import asyncio
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client


async def inspect_session(session: ClientSession) -> None:
    initialized = await session.initialize()
    tools = await session.list_tools()
    resources = await session.list_resources()
    templates = await session.list_resource_templates()
    result = await session.call_tool("get_metric_definition", {"metric_name": "success_rate"})
    print("server:", initialized.serverInfo.name, initialized.serverInfo.version)
    print("tools:", [tool.name for tool in tools.tools])
    print("resources:", [str(item.uri) for item in resources.resources])
    print("templates:", [item.uriTemplate for item in templates.resourceTemplates])
    print("result:", result.structuredContent)


async def stdio_demo() -> None:
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "mcp_lab.server", "--transport", "stdio"],
    )
    async with stdio_client(params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await inspect_session(session)


async def http_demo(url: str) -> None:
    async with streamable_http_client(url) as (read_stream, write_stream, _):
        async with ClientSession(read_stream, write_stream) as session:
            await inspect_session(session)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--transport", choices=["stdio", "streamable-http"], default="stdio")
    parser.add_argument("--url", default="http://127.0.0.1:8000/mcp")
    args = parser.parse_args()
    asyncio.run(stdio_demo() if args.transport == "stdio" else http_demo(args.url))


if __name__ == "__main__":
    main()

