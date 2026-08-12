"""在进程内通过 HTTP+JSON/REST 发现 Agent 并委托任务。"""

import asyncio
import json
from uuid import uuid4

import httpx

from a2a_lab.a2a_server import a2a_app


async def async_main() -> None:
    transport = httpx.ASGITransport(app=a2a_app)
    headers = {"A2A-Version": "1.0", "X-Tenant": "tenant-a"}
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        card = (await client.get("/.well-known/agent-card.json")).json()
        response = await client.post(
            "/a2a/message:send",
            headers=headers,
            json={
                "tenant": "tenant-a",
                "message": {
                    "messageId": uuid4().hex,
                    "role": "ROLE_USER",
                    "parts": [{"text": "收入 128000，成功率 98%，仅包含聚合数据。"}],
                },
                "configuration": {"returnImmediately": False},
                "metadata": {
                    "traceId": "trace-demo-001",
                    "idempotencyKey": "report-demo-001",
                },
            },
        )
    print("Agent Card:", card["name"], [skill["id"] for skill in card["skills"]])
    print("Task response:", json.dumps(response.json(), ensure_ascii=False, indent=2))


def main() -> None:
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
