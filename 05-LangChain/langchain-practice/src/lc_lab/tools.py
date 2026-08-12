"""业务函数与 LangChain Tool 适配。"""

from __future__ import annotations

from langchain.tools import tool
from pydantic import BaseModel, ConfigDict, Field

from lc_lab.domain import (
    DEFAULT_CATALOG,
    DEFAULT_CONTEXT,
    MetricCatalog,
    MetricNotFoundError,
    UserContext,
)


class MetricLookupInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metric_name: str = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[a-z][a-z0-9_]*$",
        description="规范化指标名，例如 success_rate 或 revenue",
    )


class ToolBudgetExceeded(RuntimeError):
    pass


class ToolCallBudget:
    def __init__(self, maximum: int) -> None:
        if maximum <= 0:
            raise ValueError("maximum 必须大于 0")
        self.maximum = maximum
        self.used = 0

    def consume(self) -> None:
        # 预算放在实际工具入口，才能在副作用发生前拦住超额调用。
        if self.used >= self.maximum:
            raise ToolBudgetExceeded(f"工具调用超过上限 {self.maximum}")
        self.used += 1


def lookup_metric(
    metric_name: str,
    *,
    context: UserContext = DEFAULT_CONTEXT,
    catalog: MetricCatalog = DEFAULT_CATALOG,
) -> str:
    """不依赖框架的业务函数，便于直接单测。"""
    try:
        return catalog.get(metric_name, context).definition
    except MetricNotFoundError:
        return "NOT_FOUND"


def build_metric_definition_tool(
    *,
    context: UserContext = DEFAULT_CONTEXT,
    catalog: MetricCatalog = DEFAULT_CATALOG,
    budget: ToolCallBudget | None = None,
):
    """将请求上下文绑定进工具，避免让模型伪造 tenant/role 参数。"""

    @tool("get_metric_definition", args_schema=MetricLookupInput)
    def metric_tool(metric_name: str) -> str:
        """查询指标的正式定义；只用于指标口径问题。"""
        if budget is not None:
            budget.consume()
        return lookup_metric(metric_name, context=context, catalog=catalog)

    return metric_tool


get_metric_definition = build_metric_definition_tool()
