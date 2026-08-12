import sys
from pathlib import Path

import pytest
from agentscope.agent import Agent, ReActConfig
from agentscope.credential import OpenAICredential
from agentscope.message import UserMsg
from agentscope.model import OpenAIChatModel
from pydantic import SecretStr

from as_lab.tools import build_toolkit


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from shared.live_llm import LiveLLMSettings  # noqa: E402


pytestmark = [pytest.mark.live, pytest.mark.asyncio]


async def test_live_agentscope_model_completes_the_real_tool_loop():
    settings = LiveLLMSettings.from_env()

    model = OpenAIChatModel(
        credential=OpenAICredential(
            name="live-test",
            api_key=SecretStr(settings.api_key),
            base_url=settings.base_url,
        ),
        model=settings.model,
        parameters=OpenAIChatModel.Parameters(
            temperature=settings.temperature,
            max_tokens=settings.max_tokens,
        ),
        stream=False,
        max_retries=1,
        client_kwargs={"timeout": settings.timeout_seconds},
    )
    agent = Agent(
        name="live_metric_agent",
        system_prompt="指标口径必须通过工具查询；拿到工具结果后用中文简短回答。",
        model=model,
        toolkit=build_toolkit(),
        react_config=ReActConfig(max_iters=3, stop_on_reject=True),
    )
    reply = await agent.reply(UserMsg(name="learner", content="营业收入 revenue 的正式定义是什么？"))
    text = reply.get_text_content()
    assert "不含税支付金额" in text
    assert "退款" in text
