"""展示 Tool schema、专家路由、跨 Agent 消息和审核结果。"""

import asyncio

from as_lab.tools import build_toolkit
from as_lab.workflow import MultiAgentCoordinator


async def async_main() -> None:
    toolkit = build_toolkit()
    print("工具 schema：", (await toolkit.get_tool_schemas())[0])

    coordinator = MultiAgentCoordinator()
    for question in ("成功率的定义是什么？", "RAG 是什么？"):
        result = await coordinator.run(question)
        print(
            {
                "request_id": result.request_id,
                "status": result.status,
                "specialist": result.specialist,
                "answer": result.answer,
                "message_flow": [
                    f"{item.sender} -> {item.receiver} ({item.kind})" for item in result.messages
                ],
            }
        )


def main() -> None:
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
