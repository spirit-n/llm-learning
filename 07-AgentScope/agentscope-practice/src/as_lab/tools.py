"""业务工具与 AgentScope 适配。"""

from typing import Any

from agentscope.permission import PermissionBehavior, PermissionDecision
from agentscope.tool import FunctionTool, Toolkit


DEFINITIONS = {
    "success_rate": "成功率 = 成功请求数 / 总请求数",
    "revenue": "营业收入 = 不含税支付金额 - 已完成退款",
}


def get_metric_definition(metric_name: str) -> str:
    """查询指标的正式定义。

    Args:
        metric_name: 指标英文名，例如 success_rate 或 revenue。
    """
    if metric_name == "admin_secret":
        raise PermissionError("无权读取受限指标")
    return DEFINITIONS.get(metric_name, "NOT_FOUND")


class ReadOnlyFunctionTool(FunctionTool):
    """本地演示用：只读函数无需交互确认。写操作不能套用此策略。"""

    async def check_permissions(self, *_args: Any, **_kwargs: Any) -> PermissionDecision:
        return PermissionDecision(behavior=PermissionBehavior.ALLOW, message="只读工具已允许")


def build_toolkit() -> Toolkit:
    tool = ReadOnlyFunctionTool(get_metric_definition, is_read_only=True)
    return Toolkit(tools=[tool])

