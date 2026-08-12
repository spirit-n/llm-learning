from __future__ import annotations

import json
import time

import pytest
from pydantic import BaseModel, ConfigDict

from tool_loop.fake_model import ScriptedFakeModel
from tool_loop.guards import GuardDenied, validate_and_rewrite_readonly_sql
from tool_loop.models import ModelResponse, ToolCall, ToolResult, UserContext
from tool_loop.registry import ToolRegistry, ToolSpec
from tool_loop.runtime import ToolRuntime
from tool_loop.tools import build_default_registry


ALL_PERMISSIONS = frozenset({"metrics:read", "schema:read", "sql:read"})


def user(*permissions: str) -> UserContext:
    return UserContext(user_id="tester", permissions=frozenset(permissions))


def scripted_tool_then_final(name: str, arguments: dict) -> ScriptedFakeModel:
    return ScriptedFakeModel(
        [
            ModelResponse(
                tool_calls=[ToolCall(id="call_1", name=name, arguments=arguments)]
            ),
            ModelResponse(final_answer="完成"),
        ]
    )


def tool_results(result) -> list[ToolResult]:
    return [
        ToolResult.model_validate_json(message.content)
        for message in result.messages
        if message.role == "tool"
    ]


def test_legal_metric_call_completes_end_to_end() -> None:
    runtime = ToolRuntime(build_default_registry())
    model = scripted_tool_then_final(
        "get_metric_definition",
        {"metric_name": "营业收入"},
    )

    result = runtime.run(model, "营业收入是什么口径？", user(*ALL_PERMISSIONS))

    assert result.status == "completed"
    assert result.final_answer == "完成"
    assert result.tool_call_count == 1
    assert result.invalid_call_count == 0
    assert tool_results(result)[0].data["version"] == "2.0"
    assert model.seen_messages[1][-1].tool_call_id == "call_1"


def test_unknown_tool_returns_controlled_error() -> None:
    runtime = ToolRuntime(build_default_registry())
    model = scripted_tool_then_final("delete_everything", {})

    result = runtime.run(model, "执行未知工具", user(*ALL_PERMISSIONS))

    assert result.status == "completed"
    assert result.invalid_call_count == 1
    assert result.audit_log[0].error_code == "UNKNOWN_TOOL"
    assert tool_results(result)[0].status == "error"


def test_missing_argument_is_rejected_by_schema() -> None:
    runtime = ToolRuntime(build_default_registry())
    model = scripted_tool_then_final("get_metric_definition", {})

    result = runtime.run(model, "缺参数", user(*ALL_PERMISSIONS))

    assert result.audit_log[0].error_code == "INVALID_ARGUMENTS"
    assert "metric_name" in tool_results(result)[0].message


def test_unexpected_argument_is_rejected_by_schema() -> None:
    runtime = ToolRuntime(build_default_registry())
    model = scripted_tool_then_final(
        "get_metric_definition",
        {"metric_name": "营业收入", "grant_admin": True},
    )

    result = runtime.run(model, "尝试注入额外参数", user(*ALL_PERMISSIONS))

    assert result.audit_log[0].error_code == "INVALID_ARGUMENTS"
    assert "grant_admin" in tool_results(result)[0].message


def test_permission_is_checked_before_execution() -> None:
    runtime = ToolRuntime(build_default_registry())
    model = scripted_tool_then_final(
        "run_readonly_sql",
        {"sql": "SELECT order_id FROM sales", "max_rows": 10},
    )

    result = runtime.run(model, "查询订单", user("metrics:read"))

    assert result.audit_log[0].outcome == "denied"
    assert result.audit_log[0].error_code == "PERMISSION_DENIED"


@pytest.mark.parametrize(
    ("sql", "error_code"),
    [
        ("DROP TABLE sales", "SQL_NOT_READONLY"),
        (
            "SELECT order_id FROM sales; DROP TABLE sales",
            "SQL_MULTIPLE_STATEMENTS",
        ),
        ("SELECT * FROM sales", "SQL_STAR_DENIED"),
        ("SELECT email FROM customers", "SQL_COLUMN_DENIED"),
        ("SELECT name FROM sqlite_master", "SQL_TABLE_DENIED"),
        ("SELECT value FROM read_csv('x')", "SQL_FUNCTION_DENIED"),
    ],
)
def test_sql_guard_rejects_dangerous_queries(sql: str, error_code: str) -> None:
    with pytest.raises(GuardDenied) as exc_info:
        validate_and_rewrite_readonly_sql(
            sql,
            max_rows=10,
            allowed_tables={"sales", "customers"},
        )

    assert exc_info.value.code == error_code


def test_sql_guard_adds_or_reduces_limit() -> None:
    added = validate_and_rewrite_readonly_sql(
        "SELECT order_id FROM sales",
        max_rows=10,
        allowed_tables={"sales"},
    )
    reduced = validate_and_rewrite_readonly_sql(
        "SELECT order_id FROM sales LIMIT 999",
        max_rows=10,
        allowed_tables={"sales"},
    )

    assert added.endswith("LIMIT 10")
    assert reduced.endswith("LIMIT 10")


def test_readonly_sql_executes_against_learning_database() -> None:
    runtime = ToolRuntime(build_default_registry())
    model = scripted_tool_then_final(
        "run_readonly_sql",
        {
            "sql": "SELECT channel, amount FROM sales ORDER BY amount DESC",
            "max_rows": 2,
        },
    )

    result = runtime.run(model, "查询收入", user(*ALL_PERMISSIONS))
    sql_result = tool_results(result)[0]

    assert sql_result.status == "ok"
    assert sql_result.data["row_count"] == 2
    assert sql_result.data["sql"].endswith("LIMIT 2")


class NoArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")


def test_tool_timeout_returns_without_exposing_exception() -> None:
    def slow_tool(_: BaseModel) -> dict:
        time.sleep(0.1)
        return {"done": True}

    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="slow_tool",
            description="测试超时",
            args_model=NoArgs,
            handler=slow_tool,
            timeout_seconds=0.01,
        )
    )
    result = ToolRuntime(registry).run(
        scripted_tool_then_final("slow_tool", {}),
        "测试超时",
        user(),
    )

    assert result.audit_log[0].error_code == "TOOL_TIMEOUT"
    assert tool_results(result)[0].message == "工具执行超时"


def test_repeated_same_call_stops_loop() -> None:
    repeated = ToolCall(
        id="call_1",
        name="get_metric_definition",
        arguments={"metric_name": "营业收入"},
    )
    model = ScriptedFakeModel(
        [
            ModelResponse(tool_calls=[repeated]),
            ModelResponse(
                tool_calls=[repeated.model_copy(update={"id": "call_2"})]
            ),
        ]
    )

    result = ToolRuntime(build_default_registry()).run(
        model,
        "重复调用",
        user(*ALL_PERMISSIONS),
    )

    assert result.status == "stopped"
    assert result.error_code == "REPEATED_TOOL_CALL"
    assert result.steps == 2


def test_large_output_is_redacted_and_truncated() -> None:
    def large_tool(_: BaseModel) -> dict:
        return {
            "api_key": "must-not-appear",
            "rows": ["x" * 500 for _ in range(10)],
        }

    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="large_tool",
            description="测试超长输出",
            args_model=NoArgs,
            handler=large_tool,
            output_limit_bytes=200,
        )
    )
    result = ToolRuntime(registry).run(
        scripted_tool_then_final("large_tool", {}),
        "测试截断",
        user(),
    )
    message_content = next(
        message.content for message in result.messages if message.role == "tool"
    )
    parsed_result = ToolResult.model_validate_json(message_content)

    assert parsed_result.truncated is True
    assert parsed_result.original_bytes > 200
    assert "must-not-appear" not in message_content
    assert "[REDACTED]" in message_content


def test_max_steps_stops_endless_unique_calls() -> None:
    model = ScriptedFakeModel(
        [
            ModelResponse(
                tool_calls=[
                    ToolCall(
                        id=f"call_{index}",
                        name="get_metric_definition",
                        arguments={"metric_name": f"不存在指标{index}"},
                    )
                ]
            )
            for index in range(3)
        ]
    )

    result = ToolRuntime(build_default_registry(), max_steps=3).run(
        model,
        "不要停止",
        user(*ALL_PERMISSIONS),
    )

    assert result.status == "max_steps"
    assert result.error_code == "MAX_STEPS_EXCEEDED"
    assert result.steps == 3
    assert result.tool_call_count == 3


def test_registry_exposes_schema_and_metadata() -> None:
    schemas = build_default_registry().model_schemas()
    sql_schema = next(
        schema for schema in schemas if schema["function"]["name"] == "run_readonly_sql"
    )

    assert sql_schema["function"]["parameters"]["additionalProperties"] is False
    assert sql_schema["metadata"]["has_side_effect"] is False
