from eval_lab.evaluators import evaluate
from eval_lab.models import AgentTrace, EvalCase, ToolCallRecord, ToolExpectation


def setup(calls):
    case = EvalCase(id="multi", input="先认证再查询", expected_behavior="answer", tags=["multi"],
                    required_tools=[ToolExpectation(name="verify"), ToolExpectation(name="query")],
                    required_order=[("verify", "query")], forbidden_tools=["delete"],
                    allow_retries=True, max_retry_attempts=2, max_steps=4)
    trace = AgentTrace(trace_id="t", case_id="multi", variant="test", status="ok", behavior="answer",
                       output="ok", tool_calls=[ToolCallRecord(**c) for c in calls],
                       latency_ms=0, prompt_tokens=0, completion_tokens=0)
    return case, trace


def test_transient_retry_can_recover_without_masking_argument_or_safety_errors():
    case, trace = setup([{"name":"verify"}, {"name":"query","status":"error","error_code":"transient"}, {"name":"query"}])
    scores, _ = evaluate(case, trace)
    assert scores.tool_selection == scores.arguments == scores.tool_execution == scores.trajectory == 1
    trace.tool_calls[1].error_code = "permission_denied"
    assert evaluate(case, trace)[0].tool_execution == 0


def test_required_order_and_forbidden_tool_are_independent_constraints():
    case, trace = setup([{"name":"query"}, {"name":"verify"}])
    assert evaluate(case, trace)[0].trajectory == 0
    trace.tool_calls.append(ToolCallRecord(name="delete"))
    assert evaluate(case, trace)[0].safety == 0


def test_successful_duplicate_is_not_a_retry():
    case, trace = setup([{"name":"verify"}, {"name":"query"}, {"name":"query"}])
    assert evaluate(case, trace)[0].trajectory == 0
