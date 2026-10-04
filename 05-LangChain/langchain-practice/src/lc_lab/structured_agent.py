"""Compare native-schema and tool-schema Agent output without a provider call."""

import json
from typing import Any, Literal

from langchain.agents import create_agent
from langchain.agents.structured_output import ProviderStrategy, ToolStrategy
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from .structured import Intent


class OfflineStructuredModel(BaseChatModel):
    """A protocol fixture, NOT evidence that a real provider supports native schemas."""
    native: bool = False
    schema_name: str = "Intent"

    @property
    def _llm_type(self):
        return "offline-structured-protocol-fixture"

    def bind_tools(self, tools, *, tool_choice=None, **kwargs: Any):
        name = next((getattr(tool, "name", None) for tool in tools if getattr(tool, "name", None)), "Intent")
        return self.model_copy(update={"native": "response_format" in kwargs, "schema_name": name})

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        value = {"category": "knowledge", "reason": "询问指标定义", "confidence": 0.9}
        if self.native:
            message = AIMessage(content=json.dumps(value, ensure_ascii=False))
        else:
            message = AIMessage(content="", tool_calls=[{
                "name": self.schema_name, "args": value, "id": "structured-1", "type": "tool_call",
            }])
        return ChatResult(generations=[ChatGeneration(message=message)])


def build_structured_agent(model: BaseChatModel, *, strategy: Literal["tool", "provider"],
                           provider_native_supported: bool = False):
    if strategy == "provider":
        if not provider_native_supported:
            raise ValueError("ProviderStrategy requires verified provider/model native-schema support")
        response_format = ProviderStrategy(Intent)
    elif strategy == "tool":
        # Disable hidden repair loops in this first experiment. Production retries need a budget.
        response_format = ToolStrategy(Intent, handle_errors=False)
    else:
        raise ValueError("strategy must be tool or provider")
    return create_agent(model=model, tools=[], response_format=response_format)


def main():
    for strategy in ("tool", "provider"):
        agent = build_structured_agent(OfflineStructuredModel(), strategy=strategy,
                                       provider_native_supported=(strategy == "provider"))
        result = agent.invoke({"messages": [{"role": "user", "content": "成功率是什么？"}]},
                              config={"recursion_limit": 6})
        print(strategy, result["structured_response"].model_dump())


if __name__ == "__main__":
    main()
