"""指标领域模型。

这一层刻意不 import LangChain：业务权限和数据契约不能被框架生命周期绑死。
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class DomainModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class UserContext(DomainModel):
    tenant: str = Field(min_length=1)
    roles: frozenset[str] = frozenset({"analyst"})


class MetricDefinition(DomainModel):
    name: str
    definition: str
    tenant: str
    required_role: str = "analyst"
    version: str


class MetricNotFoundError(LookupError):
    pass


class MetricPermissionError(PermissionError):
    pass


class MetricCatalog:
    def __init__(self, definitions: list[MetricDefinition]) -> None:
        keys = [(item.tenant, item.name) for item in definitions]
        if len(keys) != len(set(keys)):
            raise ValueError("同一 tenant 下 metric name 必须唯一")
        self._definitions = {(item.tenant, item.name): item for item in definitions}

    def get(self, metric_name: str, context: UserContext) -> MetricDefinition:
        normalized = metric_name.strip().lower()
        item = self._definitions.get((context.tenant, normalized))
        if item is None:
            # 不回退到其他 tenant；否则“查不到”分支可能变成数据越权。
            raise MetricNotFoundError(f"指标不存在: {normalized}")
        if item.required_role not in context.roles:
            raise MetricPermissionError(
                f"角色 {item.required_role} 才能访问指标 {normalized}"
            )
        return item


DEFAULT_CATALOG = MetricCatalog(
    [
        MetricDefinition(
            name="success_rate",
            definition="成功率 = 成功请求数 / 总请求数",
            tenant="demo",
            version="2.1",
        ),
        MetricDefinition(
            name="revenue",
            definition="营业收入 = 不含税支付金额 - 已完成退款",
            tenant="demo",
            version="2.0",
        ),
        MetricDefinition(
            name="admin_secret",
            definition="内部审计阈值",
            tenant="demo",
            required_role="admin",
            version="1.0",
        ),
    ]
)


DEFAULT_CONTEXT = UserContext(tenant="demo")
