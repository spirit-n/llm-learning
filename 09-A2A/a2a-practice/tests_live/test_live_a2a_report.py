import asyncio
import sys
from pathlib import Path
from uuid import uuid4

import httpx
import pytest

from a2a_lab.a2a_server import build_a2a_app


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from shared.live_llm import (  # noqa: E402
    LiveLLMSettings,
    OpenAICompatibleChatClient,
)


pytestmark = [
    pytest.mark.live,
    pytest.mark.asyncio,
    pytest.mark.filterwarnings(
        r"ignore:label\(\) is deprecated.*:DeprecationWarning:a2a\.utils\.proto_utils"
    ),
]


async def test_live_report_generator_runs_behind_the_a2a_boundary():
    settings = LiveLLMSettings.from_env()
    llm = OpenAICompatibleChatClient(settings)

    async def generate(summary: str) -> str:
        message = await asyncio.to_thread(
            llm.chat,
            [
                {
                    "role": "system",
                    "content": "把聚合指标写成简短 Markdown 管理报告，必须包含标题、数据摘要和结论，不添加输入外的数字。",
                },
                {"role": "user", "content": summary},
            ],
        )
        return message["content"]

    app = build_a2a_app(report_generator=generate)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/a2a/message:send",
            headers={"A2A-Version": "1.0", "X-Tenant": "tenant-a"},
            json={
                "tenant": "tenant-a",
                "message": {
                    "messageId": uuid4().hex,
                    "role": "ROLE_USER",
                    "parts": [{"text": "收入 128000，成功率 98%，仅聚合数据。"}],
                },
                "configuration": {"returnImmediately": False},
                "metadata": {"traceId": "trace-live"},
            },
        )
    assert response.status_code == 200, response.text
    task = response.json()["task"]
    assert task["status"]["state"] == "TASK_STATE_COMPLETED"
    artifact = task["artifacts"][0]
    assert artifact["name"] == "management-report.md"
    report = artifact["parts"][0]["text"]
    normalized_report = report.replace(",", "").replace("，", "")
    assert "128000" in normalized_report
    assert "98%" in report
