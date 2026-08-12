"""确定性 routing：先分类，再把同一条 Msg 交给目标 Agent。"""

from dataclasses import dataclass
from typing import Literal

from agentscope.message import Msg, UserMsg

from as_lab.agents import build_knowledge_agent, build_metric_agent


@dataclass(frozen=True)
class RouteResult:
    target: Literal["metric_agent", "knowledge_agent"]
    request: Msg
    response: Msg


def choose_agent(question: str) -> Literal["metric_agent", "knowledge_agent"]:
    metric_words = ("指标", "成功率", "收入", "revenue", "success_rate")
    return "metric_agent" if any(word in question.lower() for word in metric_words) else "knowledge_agent"


async def route_request(question: str) -> RouteResult:
    request = UserMsg(name="learner", content=question)
    target = choose_agent(question)
    agent = build_metric_agent() if target == "metric_agent" else build_knowledge_agent()
    response = await agent.reply(request)
    return RouteResult(target=target, request=request, response=response)

