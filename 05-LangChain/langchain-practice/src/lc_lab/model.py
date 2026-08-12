"""可预测的离线 ChatModel，用来观察 Agent 循环而不消耗 API。"""

from typing import Any, Sequence

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import Runnable


class DemoChatModel(BaseChatModel):
    """先请求指标工具，收到 ToolMessage 后再组织最终回答。"""

    bound_tool_names: tuple[str, ...] = ()

    @property
    def _llm_type(self) -> str:
        return "deterministic-demo-chat-model"

    def bind_tools(
        self,
        tools: Sequence[Any],
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> Runnable:
        names = tuple(getattr(item, "name", str(item)) for item in tools)
        return self.model_copy(update={"bound_tool_names": names})

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        last = messages[-1]
        if isinstance(last, ToolMessage):
            if str(last.content) == "NOT_FOUND":
                message = AIMessage(content="没有找到该指标的正式口径，无法回答。")
            else:
                message = AIMessage(content=f"查询结果：{last.content}")
        else:
            text = str(last.content).lower()
            if "admin" in text or "秘密" in text:
                metric = "admin_secret"
            elif "收入" in text or "revenue" in text:
                metric = "revenue"
            elif "不存在" in text or "unknown" in text:
                metric = "unknown_metric"
            else:
                metric = "success_rate"
            message = AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "get_metric_definition",
                        "args": {"metric_name": metric},
                        "id": "demo-call-1",
                        "type": "tool_call",
                    }
                ],
            )
        return ChatResult(generations=[ChatGeneration(message=message)])


class LoopingChatModel(DemoChatModel):
    """故意永远调用工具，用来验证递归上限确实能停止失控 Agent。"""

    @property
    def _llm_type(self) -> str:
        return "deterministic-looping-chat-model"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        message = AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "get_metric_definition",
                    "args": {"metric_name": "success_rate"},
                    "id": f"loop-{len(messages)}",
                    "type": "tool_call",
                }
            ],
        )
        return ChatResult(generations=[ChatGeneration(message=message)])
