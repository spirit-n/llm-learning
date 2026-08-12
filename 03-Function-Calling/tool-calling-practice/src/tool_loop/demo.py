from __future__ import annotations

from .fake_model import ScriptedFakeModel
from .models import ModelResponse, ToolCall, UserContext
from .runtime import ToolRuntime
from .tools import build_default_registry


def main() -> None:
    model = ScriptedFakeModel(
        [
            ModelResponse(
                tool_calls=[
                    ToolCall(
                        id="call_metric",
                        name="get_metric_definition",
                        arguments={"metric_name": "营业收入"},
                    )
                ]
            ),
            ModelResponse(
                tool_calls=[
                    ToolCall(
                        id="call_schema",
                        name="describe_table",
                        arguments={"table": "sales"},
                    )
                ]
            ),
            ModelResponse(
                tool_calls=[
                    ToolCall(
                        id="call_sql",
                        name="run_readonly_sql",
                        arguments={
                            "sql": "SELECT channel, SUM(amount) AS revenue FROM sales GROUP BY channel ORDER BY revenue DESC",
                            "max_rows": 10,
                        },
                    )
                ]
            ),
            ModelResponse(final_answer="已读取指标口径，并按渠道查询了学习库中的收入。"),
        ]
    )
    user = UserContext(
        user_id="student",
        permissions=frozenset({"metrics:read", "schema:read", "sql:read"}),
    )
    result = ToolRuntime(build_default_registry()).run(
        model,
        "查询营业收入口径，并按渠道汇总收入。",
        user,
    )

    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    main()

