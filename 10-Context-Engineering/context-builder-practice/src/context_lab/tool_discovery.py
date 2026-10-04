"""轻量目录 → 确定性搜索 → 按需 schema 的离线对照，不调用模型或工具。"""

import json
from dataclasses import dataclass

from context_lab.builder import estimate_tokens


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    keywords: tuple[str, ...]
    required_scope: str
    input_schema: dict[str, object]


class DeferredToolCatalog:
    def __init__(self, tools: list[ToolDefinition], *, scopes: frozenset[str]):
        # 权限先于目录暴露和搜索；schema 延迟加载不是授权手段。
        visible = [tool for tool in tools if tool.required_scope in scopes]
        if len({tool.name for tool in visible}) != len(visible):
            raise ValueError("duplicate tool name")
        self._tools = {tool.name: tool for tool in visible}
        self.loaded_schema_names: list[str] = []

    def lightweight_index(self) -> list[dict[str, str]]:
        return [{"name": tool.name, "description": tool.description}
                for tool in self._tools.values()]

    def search(self, query: str) -> tuple[str, ...]:
        query = query.casefold()
        return tuple(tool.name for tool in self._tools.values()
                     if any(keyword.casefold() in query for keyword in tool.keywords))

    def load_schema(self, name: str) -> dict[str, object]:
        if name not in self._tools:
            raise PermissionError("tool unavailable")
        if name not in self.loaded_schema_names:
            self.loaded_schema_names.append(name)
        tool = self._tools[name]
        return {"name": tool.name, "description": tool.description,
                "parameters": json.loads(json.dumps(tool.input_schema))}


def run_tool_discovery_experiment() -> dict[str, object]:
    schema = {"type": "object", "properties": {
        f"filter_{i}": {"type": "string", "description": "可选业务过滤字段，调用前需验证权限和合法取值。"}
        for i in range(12)
    }, "additionalProperties": False}
    tools = [ToolDefinition(f"catalog_{i}", f"读取业务目录 {i}", (f"category-{i}",),
                            "catalog:read", schema) for i in range(30)]
    tools += [ToolDefinition("metric_definition", "读取成功率正式定义", ("成功率",),
                             "catalog:read", schema),
              ToolDefinition("delete_metrics", "删除指标数据", ("成功率",), "admin:write", schema)]
    scopes = frozenset({"catalog:read"})
    eager = DeferredToolCatalog(tools, scopes=scopes)
    all_schemas = [eager.load_schema(row["name"]) for row in eager.lightweight_index()]
    lazy = DeferredToolCatalog(tools, scopes=scopes)
    index = lazy.lightweight_index()
    selected = lazy.search("查询成功率正式定义")
    schemas = [lazy.load_schema(name) for name in selected]
    expected = {"metric_definition"}
    hits = expected.intersection(selected)
    tokens = lambda value: estimate_tokens(json.dumps(value, ensure_ascii=False))
    return {
        "visible_tools": len(index), "selected_tools": list(selected),
        "tool_recall": len(hits) / len(expected),
        "tool_precision": len(hits) / len(selected) if selected else 0.0,
        "eager_definition_tokens": tokens(all_schemas),
        "deferred_definition_tokens": tokens(index) + tokens(schemas),
        "schemas_loaded": lazy.loaded_schema_names,
        "extra_discovery_steps": 2,  # 搜索与 schema 加载；不是测得的网络延迟。
        "router": "deterministic_keywords_not_model_eval",
    }


if __name__ == "__main__":
    print(json.dumps(run_tool_discovery_experiment(), ensure_ascii=False, indent=2))
