"""组装职责隔离的专家 Agent 和审核 Agent。"""

from agentscope.agent import Agent, ReActConfig

from as_lab.model import OfflineChatModel
from as_lab.tools import build_toolkit


def build_metric_agent() -> Agent:
    return Agent(
        name="metric_agent",
        system_prompt="你是指标助手，必须通过工具查询正式口径。",
        model=OfflineChatModel("metric"),
        toolkit=build_toolkit(),
        react_config=ReActConfig(max_iters=3, stop_on_reject=True),
    )


def build_knowledge_agent() -> Agent:
    return Agent(
        name="knowledge_agent",
        system_prompt="你只解释 LLM/RAG 基础知识，不调用业务工具。",
        model=OfflineChatModel("knowledge"),
        react_config=ReActConfig(max_iters=1),
    )


def build_review_agent() -> Agent:
    """审核者不拥有业务工具，避免它在审核阶段偷偷扩大数据访问范围。"""

    return Agent(
        name="review_agent",
        system_prompt=(
            "检查专家草稿是否回答问题、是否包含工具错误或未找到标记。"
            "通过时输出 APPROVED 加最终答案，否则输出 REJECTED 加原因。"
        ),
        model=OfflineChatModel("reviewer"),
        react_config=ReActConfig(max_iters=1),
    )
