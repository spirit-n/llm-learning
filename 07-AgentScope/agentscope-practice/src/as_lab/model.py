"""AgentScope ChatModelBase 的离线实现。"""

import json
from typing import Any, Literal

from agentscope.credential import CredentialBase
from agentscope.message import Msg, TextBlock, ToolCallBlock, ToolResultBlock
from agentscope.model import ChatModelBase, ChatResponse
from agentscope.tool import ToolChoice


class OfflineChatModel(ChatModelBase):
    """可预测模型：metric 模式调用工具，knowledge 模式直接回答。"""

    class Parameters(ChatModelBase.Parameters):
        pass

    def __init__(self, mode: Literal["metric", "knowledge", "reviewer"]):
        super().__init__(
            credential=CredentialBase(name="offline-no-secret"),
            model=f"offline-{mode}",
            parameters=self.Parameters(),
            stream=False,
            max_retries=0,
        )
        self.mode = mode

    async def _call_api(
        self,
        model_name: str,
        messages: list[Msg],
        tools: list[dict] | None = None,
        tool_choice: ToolChoice | None = None,
        **kwargs: Any,
    ) -> ChatResponse:
        if self.mode == "reviewer":
            review_input = "\n".join(
                message.get_text_content() for message in messages if message.role == "user"
            )
            draft = review_input.partition("[draft]\n")[2].strip()
            if not draft or "NOT_FOUND" in draft or "PermissionError" in draft:
                text = "REJECTED: 草稿没有得到有效、获授权的依据"
            else:
                text = f"APPROVED\n{draft}"
            return ChatResponse(content=[TextBlock(text=text)], is_last=True)

        if self.mode == "knowledge":
            return ChatResponse(
                content=[TextBlock(text="RAG 通过检索外部证据来补充模型上下文。")],
                is_last=True,
            )

        tool_results = [
            block
            for message in messages
            for block in message.content
            if isinstance(block, ToolResultBlock)
        ]
        if tool_results:
            output = tool_results[-1].output
            if isinstance(output, list):
                text = "".join(block.text for block in output if isinstance(block, TextBlock))
            else:
                text = output
            return ChatResponse(content=[TextBlock(text=f"工具结果：{text}")], is_last=True)

        question = " ".join(message.get_text_content() for message in messages if message.role == "user")
        metric = "revenue" if "收入" in question or "revenue" in question.lower() else "success_rate"
        return ChatResponse(
            content=[
                ToolCallBlock(
                    id="offline-tool-call-1",
                    name="get_metric_definition",
                    input=json.dumps({"metric_name": metric}, ensure_ascii=False),
                )
            ],
            is_last=True,
        )
