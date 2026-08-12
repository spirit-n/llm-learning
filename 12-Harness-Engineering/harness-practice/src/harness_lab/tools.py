from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from .errors import TransientToolError
from .registry import ToolRegistry, ToolSpec


class MetricArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    metric_name: str = Field(min_length=1, max_length=100)


class QueryArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    metric_name: str = Field(min_length=1, max_length=100)
    tenant: str = Field(min_length=1, max_length=100)


class DemoTools:
    def __init__(self, *, transient_failures: int = 0, empty: bool = False, anomalous: bool = False):
        self.transient_failures = transient_failures
        self.empty = empty
        self.anomalous = anomalous
        self.query_calls = 0

    @staticmethod
    def get_metric_definition(args: MetricArgs) -> dict:
        definitions = {"success_rate": "成功率 = 成功请求数 / 总请求数"}
        return {"metric_name": args.metric_name, "definition": definitions.get(args.metric_name, "NOT_FOUND")}

    def query_metric(self, args: QueryArgs) -> dict:
        self.query_calls += 1
        if self.query_calls <= self.transient_failures:
            raise TransientToolError("模拟数据库瞬时断连")
        if self.empty:
            return {"tenant": args.tenant, "rows": []}
        value = 1.5 if self.anomalous else 0.98
        return {"tenant": args.tenant, "rows": [{"metric": args.metric_name, "value": value}]}


def build_demo_registry(tools: DemoTools | None = None) -> ToolRegistry:
    implementation = tools or DemoTools()
    return ToolRegistry(
        [
            ToolSpec(
                name="get_metric_definition",
                description="读取指标正式口径",
                args_model=MetricArgs,
                handler=implementation.get_metric_definition,
                required_permission="metrics:read",
            ),
            ToolSpec(
                name="query_metric",
                description="查询租户聚合指标",
                args_model=QueryArgs,
                handler=implementation.query_metric,
                required_permission="metrics:query",
                cost_units=2,
                version="2.1",
                risk_level="medium",
                # tenant 不能只靠 Planner 自觉填写，Harness 会把它和登录用户作用域比对。
                tenant_argument="tenant",
            ),
        ]
    )
