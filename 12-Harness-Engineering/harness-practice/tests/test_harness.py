import time
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from pydantic import BaseModel

from harness_lab.errors import TransientToolError
from harness_lab.models import Observation, PlanDecision, TaskSpec, UserContext, Verification
from harness_lab.planner import ScriptedPlanner
from harness_lab.registry import ToolRegistry, ToolSpec
from harness_lab.runtime import AgentHarness
from harness_lab.tools import DemoTools, build_demo_registry
from harness_lab.trace import TraceRecorder
from harness_lab.verifiers import verify_metric_answer


def task(**updates) -> TaskSpec:
    values = {
        "task_id": "t-1",
        "objective": "查询成功率",
        "expected_metric": "success_rate",
        "allowed_tools": frozenset({"query_metric"}),
    }
    values.update(updates)
    return TaskSpec(**values)


def user(*permissions: str) -> UserContext:
    return UserContext(user_id="u-1", tenant="tenant-a", permissions=frozenset(permissions))


def successful_planner(answer: str = "昨日成功率为 98%。") -> ScriptedPlanner:
    return ScriptedPlanner(
        [
            PlanDecision(kind="tool", tool_name="query_metric", arguments={"metric_name": "success_rate", "tenant": "tenant-a"}),
            PlanDecision(kind="final", answer=answer),
        ]
    )


def harness(tools: DemoTools | None = None) -> AgentHarness:
    return AgentHarness(build_demo_registry(tools), verify_metric_answer)


def test_success_path_has_observation_verification_and_trace():
    result = harness().run(successful_planner(), task(), user("metrics:query"))
    assert result.status == "succeeded"
    assert result.answer == "昨日成功率为 98%。"
    assert result.steps == 2
    assert result.cost_units == 4
    assert [event.event for event in result.trace][-1] == "verification"


def test_context_budget_rejects_before_planner_or_tool():
    planner = successful_planner()
    result = harness().run(planner, task(context="x" * 20, max_context_chars=10), user("metrics:query"))
    assert result.error_code == "CONTEXT_BUDGET_EXCEEDED"
    assert planner.calls == 0


def test_tool_must_be_in_task_allowlist():
    planner = ScriptedPlanner([PlanDecision(kind="tool", tool_name="query_metric", arguments={})])
    result = harness().run(planner, task(allowed_tools=frozenset()), user("metrics:query"))
    assert result.error_code == "TOOL_NOT_ALLOWED"


def test_permission_denial_is_not_retried():
    result = harness().run(successful_planner(), task(), user())
    assert result.error_code == "PERMISSION_DENIED"
    assert result.steps == 1


def test_invalid_arguments_are_rejected_before_handler():
    implementation = DemoTools()
    planner = ScriptedPlanner([PlanDecision(kind="tool", tool_name="query_metric", arguments={"metric_name": "success_rate"})])
    result = harness(implementation).run(planner, task(), user("metrics:query"))
    assert result.error_code == "INVALID_ARGUMENTS"
    assert implementation.query_calls == 0


def test_transient_tool_failure_is_retried_within_budget():
    implementation = DemoTools(transient_failures=1)
    result = harness(implementation).run(successful_planner(), task(max_transient_retries=1), user("metrics:query"))
    assert result.status == "succeeded"
    assert implementation.query_calls == 2
    assert result.cost_units == 6
    assert any(event.event == "tool_retry" for event in result.trace)


def test_transient_retry_exhaustion_has_stable_error():
    implementation = DemoTools(transient_failures=3)
    result = harness(implementation).run(successful_planner(), task(max_transient_retries=1), user("metrics:query"))
    assert result.status == "failed"
    assert result.error_code == "TOOL_TRANSIENT"
    assert implementation.query_calls == 2


def test_empty_and_anomalous_results_fail_in_verifier():
    empty = harness(DemoTools(empty=True)).run(successful_planner(), task(), user("metrics:query"))
    anomalous = harness(DemoTools(anomalous=True)).run(successful_planner("成功率为 150%。"), task(), user("metrics:query"))
    assert empty.error_code == "EMPTY_RESULT"
    assert anomalous.error_code == "RESULT_ANOMALY"


def test_answer_must_match_tool_result():
    result = harness().run(successful_planner("昨日成功率为 80%。"), task(), user("metrics:query"))
    assert result.error_code == "ANSWER_MISMATCH"


def test_step_and_cost_budgets_stop_cleanly():
    step_result = harness().run(successful_planner(), task(max_steps=1), user("metrics:query"))
    cost_tools = DemoTools()
    cost_result = harness(cost_tools).run(successful_planner(), task(max_cost_units=2), user("metrics:query"))
    assert step_result.error_code == "MAX_STEPS_EXCEEDED"
    assert cost_result.error_code == "COST_BUDGET_EXCEEDED"
    assert cost_tools.query_calls == 0


def test_repeated_identical_call_stops_loop():
    call = PlanDecision(kind="tool", tool_name="query_metric", arguments={"metric_name": "success_rate", "tenant": "tenant-a"})
    result = harness().run(ScriptedPlanner([call, call]), task(), user("metrics:query"))
    assert result.error_code == "REPEATED_TOOL_CALL"


def test_planner_timeout_has_limited_retry():
    class SlowPlanner:
        calls = 0

        def decide(self, task, observations, tool_schemas):
            del task, observations, tool_schemas
            self.calls += 1
            time.sleep(0.03)
            return PlanDecision(kind="final", answer="late")

    planner = SlowPlanner()
    result = harness().run(planner, task(planner_timeout_seconds=0.001, max_transient_retries=1), user())
    assert result.error_code == "MODEL_TIMEOUT"
    assert planner.calls == 2


def test_side_effect_requires_explicit_approval():
    class WriteArgs(BaseModel):
        value: str

    calls = []
    registry = ToolRegistry(
        [ToolSpec(name="write", description="write", args_model=WriteArgs, handler=lambda args: calls.append(args.value), has_side_effect=True)]
    )
    agent = AgentHarness(registry, lambda task, answer, observations: Verification(passed=True, code="OK", message="ok"))
    planner = lambda: ScriptedPlanner([PlanDecision(kind="tool", tool_name="write", arguments={"value": "x"})])
    spec = task(allowed_tools=frozenset({"write"}))
    waiting = agent.run(planner(), spec, user())
    rejected = agent.run(planner(), spec, user(), approval=lambda *_: False)
    assert waiting.status == "waiting_approval"
    assert rejected.status == "cancelled"
    assert calls == []


def test_trace_redacts_secrets_and_truncates_large_text():
    trace = TraceRecorder()
    trace.add(
        "request",
        api_key="secret-value",
        authorization="Bearer abcdefghijklmnop",
        note="header was Bearer abcdefghijklmnop",
        payload="x" * 700,
        prompt_tokens=123,
    )
    details = trace.events[0].details
    assert details["api_key"] == "[REDACTED]"
    assert details["authorization"] == "[REDACTED]"
    assert "abcdefghijklmnop" not in details["note"]
    assert details["payload"].endswith("…[TRUNCATED]")
    assert details["prompt_tokens"] == 123


def test_tenant_scope_is_enforced_outside_the_planner():
    planner = ScriptedPlanner(
        [
            PlanDecision(
                kind="tool",
                tool_name="query_metric",
                arguments={"metric_name": "success_rate", "tenant": "tenant-b"},
            )
        ]
    )
    result = harness().run(planner, task(), user("metrics:query"))
    assert result.error_code == "TENANT_SCOPE_VIOLATION"


def test_cancel_check_stops_before_planner_execution():
    planner = successful_planner()
    result = harness().run(planner, task(), user("metrics:query"), cancelled=lambda: True)
    assert result.status == "cancelled"
    assert result.error_code == "USER_CANCELLED"
    assert planner.calls == 0


def test_total_deadline_is_stricter_than_planner_timeout():
    class SlowPlanner:
        def decide(self, task, observations, tool_schemas):
            del task, observations, tool_schemas
            time.sleep(0.03)
            return PlanDecision(kind="final", answer="too late")

    result = harness().run(
        SlowPlanner(),
        task(deadline_seconds=0.001, planner_timeout_seconds=1),
        user("metrics:query"),
    )
    assert result.error_code == "TASK_DEADLINE_EXCEEDED"


def test_previous_observations_survive_a_later_tool_failure():
    planner = ScriptedPlanner(
        [
            PlanDecision(
                kind="tool",
                tool_name="query_metric",
                arguments={"metric_name": "success_rate", "tenant": "tenant-a"},
            ),
            PlanDecision(kind="tool", tool_name="missing_tool", arguments={}),
        ]
    )
    result = harness().run(
        planner,
        task(allowed_tools=frozenset({"query_metric", "missing_tool"})),
        user("metrics:query"),
    )
    assert result.error_code == "UNKNOWN_TOOL"
    assert [item.tool_name for item in result.observations] == ["query_metric"]


def test_planner_output_is_runtime_validated():
    class InvalidPlanner:
        def decide(self, task, observations, tool_schemas):
            del task, observations, tool_schemas
            return {"kind": "tool", "arguments": {}}

    result = harness().run(InvalidPlanner(), task(), user("metrics:query"))
    assert result.error_code == "PLANNER_CONTRACT_INVALID"


def test_tool_output_size_limit_prevents_context_flooding():
    class NoArgs(BaseModel):
        pass

    registry = ToolRegistry(
        [
            ToolSpec(
                name="huge",
                description="huge",
                args_model=NoArgs,
                handler=lambda _: {"text": "x" * 100},
                max_output_chars=20,
            )
        ]
    )
    agent = AgentHarness(registry, lambda *_: Verification(passed=True, code="OK", message="ok"))
    result = agent.run(
        ScriptedPlanner([PlanDecision(kind="tool", tool_name="huge", arguments={})]),
        task(allowed_tools=frozenset({"huge"})),
        user(),
    )
    assert result.error_code == "TOOL_OUTPUT_TOO_LARGE"


def test_side_effect_is_replayed_by_idempotency_key_across_runs():
    class WriteArgs(BaseModel):
        request_id: str
        value: str

    calls: list[str] = []
    registry = ToolRegistry(
        [
            ToolSpec(
                name="write",
                description="write",
                args_model=WriteArgs,
                handler=lambda args: calls.append(args.value) or {"written": args.value},
                has_side_effect=True,
                idempotency_field="request_id",
                risk_level="high",
            )
        ]
    )
    agent = AgentHarness(registry, lambda *_: Verification(passed=True, code="OK", message="ok"))

    def planner(value: str):
        return ScriptedPlanner(
            [
                PlanDecision(kind="tool", tool_name="write", arguments={"request_id": "req-1", "value": value}),
                PlanDecision(kind="final", answer="done"),
            ]
        )

    spec = task(allowed_tools=frozenset({"write"}))
    first = agent.run(planner("x"), spec, user(), approval=lambda *_: True)
    replay = agent.run(planner("x"), spec, user(), approval=lambda *_: True)
    conflict = agent.run(planner("changed"), spec, user(), approval=lambda *_: True)
    assert first.status == replay.status == "succeeded"
    assert calls == ["x"]
    assert any(event.event == "tool_replayed" for event in replay.trace)
    assert conflict.error_code == "IDEMPOTENCY_CONFLICT"


def test_non_idempotent_side_effect_is_not_automatically_retried():
    class WriteArgs(BaseModel):
        value: str

    calls = 0

    def unstable(_: WriteArgs):
        nonlocal calls
        calls += 1
        raise TransientToolError()

    registry = ToolRegistry(
        [ToolSpec(name="write", description="write", args_model=WriteArgs, handler=unstable, has_side_effect=True)]
    )
    result = AgentHarness(registry, lambda *_: Verification(passed=True, code="OK", message="ok")).run(
        ScriptedPlanner([PlanDecision(kind="tool", tool_name="write", arguments={"value": "x"})]),
        task(allowed_tools=frozenset({"write"}), max_transient_retries=2),
        user(),
        approval=lambda *_: True,
    )
    assert result.error_code == "UNSAFE_RETRY_BLOCKED"
    assert calls == 1


def test_context_budget_includes_tool_schemas_and_growing_observations():
    class NoArgs(BaseModel):
        pass

    calls = 0

    def large_result(_: NoArgs):
        nonlocal calls
        calls += 1
        return {"blob": "x" * 4_000}

    registry = ToolRegistry(
        [ToolSpec(name="large", description="返回较大结果", args_model=NoArgs, handler=large_result, max_output_chars=5_000)]
    )
    planner = ScriptedPlanner(
        [
            PlanDecision(kind="tool", tool_name="large", arguments={}),
            PlanDecision(kind="final", answer="不应执行到这里"),
        ]
    )
    result = AgentHarness(registry, lambda *_: Verification(passed=True, code="OK", message="ok")).run(
        planner,
        task(allowed_tools=frozenset({"large"}), max_context_chars=2_000),
        user(),
    )
    assert result.error_code == "CONTEXT_BUDGET_EXCEEDED"
    assert calls == 1
    assert planner.calls == 1
    assert len(result.observations) == 1


def test_verifier_has_its_own_timeout_and_contract_validation():
    def slow_verifier(task, answer, observations):
        del task, answer, observations
        time.sleep(0.03)
        return Verification(passed=True, code="OK", message="late")

    timed_out = AgentHarness(build_demo_registry(), slow_verifier).run(
        successful_planner(),
        task(verifier_timeout_seconds=0.001),
        user("metrics:query"),
    )
    invalid = AgentHarness(build_demo_registry(), lambda *_: {"passed": "yes"}).run(
        successful_planner(),
        task(),
        user("metrics:query"),
    )
    assert timed_out.error_code == "VERIFIER_TIMEOUT"
    assert invalid.error_code == "VERIFIER_CONTRACT_INVALID"


def test_total_deadline_also_covers_verifier():
    def slow_verifier(task, answer, observations):
        del task, answer, observations
        time.sleep(0.03)
        return Verification(passed=True, code="OK", message="late")

    result = AgentHarness(build_demo_registry(), slow_verifier).run(
        successful_planner(),
        task(deadline_seconds=0.01, verifier_timeout_seconds=1),
        user("metrics:query"),
    )
    assert result.error_code == "TASK_DEADLINE_EXCEEDED"


def test_approval_timeout_error_and_contract_are_controlled():
    class WriteArgs(BaseModel):
        value: str

    calls = 0

    def write(_: WriteArgs):
        nonlocal calls
        calls += 1
        return {"ok": True}

    registry = ToolRegistry(
        [ToolSpec(name="write", description="写入", args_model=WriteArgs, handler=write, has_side_effect=True)]
    )
    agent = AgentHarness(registry, lambda *_: Verification(passed=True, code="OK", message="ok"))
    plan = lambda: ScriptedPlanner([PlanDecision(kind="tool", tool_name="write", arguments={"value": "x"})])
    spec = task(allowed_tools=frozenset({"write"}), approval_timeout_seconds=0.001)

    def slow_approval(*_):
        time.sleep(0.03)
        return True

    timed_out = agent.run(plan(), spec, user(), approval=slow_approval)
    invalid = agent.run(plan(), task(allowed_tools=frozenset({"write"})), user(), approval=lambda *_: "yes")
    assert timed_out.error_code == "APPROVAL_TIMEOUT"
    assert invalid.error_code == "APPROVAL_CONTRACT_INVALID"
    assert calls == 0


def test_idempotent_side_effect_timeout_never_auto_retries_and_late_result_is_replayable():
    class WriteArgs(BaseModel):
        request_id: str

    calls = 0

    def slow_write(_: WriteArgs):
        nonlocal calls
        calls += 1
        time.sleep(0.03)
        return {"written": True}

    registry = ToolRegistry(
        [
            ToolSpec(
                name="write",
                description="慢写入",
                args_model=WriteArgs,
                handler=slow_write,
                has_side_effect=True,
                idempotency_field="request_id",
                timeout_seconds=0.001,
            )
        ]
    )
    agent = AgentHarness(registry, lambda *_: Verification(passed=True, code="OK", message="ok"))

    def plan():
        return ScriptedPlanner(
            [
                PlanDecision(kind="tool", tool_name="write", arguments={"request_id": "req-timeout"}),
                PlanDecision(kind="final", answer="done"),
            ]
        )

    spec = task(allowed_tools=frozenset({"write"}), max_transient_retries=3)
    first = agent.run(plan(), spec, user(), approval=lambda *_: True)
    immediate = agent.run(plan(), spec, user(), approval=lambda *_: True)
    time.sleep(0.04)  # 原线程完成后会在线程内部提交幂等结果。
    replay = agent.run(plan(), spec, user(), approval=lambda *_: True)
    assert first.error_code == "SIDE_EFFECT_OUTCOME_UNKNOWN"
    assert immediate.error_code == "IDEMPOTENCY_IN_PROGRESS"
    assert replay.status == "succeeded"
    assert calls == 1
    assert any(event.event == "tool_replayed" for event in replay.trace)


def test_verifier_rejects_missing_non_numeric_boolean_and_non_finite_values():
    bad_rows = [
        {"metric": "success_rate"},
        {"metric": "success_rate", "value": "0.98"},
        {"metric": "success_rate", "value": True},
        {"metric": "success_rate", "value": float("nan")},
    ]
    for row in bad_rows:
        verification = verify_metric_answer(
            task(),
            "昨日成功率为 98%。",
            [Observation(tool_name="query_metric", status="ok", data={"rows": [row]})],
        )
        assert verification.code == "RESULT_SCHEMA_INVALID"


def test_atomic_idempotency_reservation_blocks_concurrent_duplicate_workers():
    class WriteArgs(BaseModel):
        request_id: str

    started = Event()
    release = Event()
    calls = 0

    def blocking_write(_: WriteArgs):
        nonlocal calls
        calls += 1
        started.set()
        assert release.wait(timeout=1)
        return {"written": True}

    registry = ToolRegistry(
        [
            ToolSpec(
                name="write",
                description="并发写入",
                args_model=WriteArgs,
                handler=blocking_write,
                has_side_effect=True,
                idempotency_field="request_id",
                timeout_seconds=1,
            )
        ]
    )
    agent = AgentHarness(registry, lambda *_: Verification(passed=True, code="OK", message="ok"))

    def plan():
        return ScriptedPlanner(
            [
                PlanDecision(kind="tool", tool_name="write", arguments={"request_id": "same-request"}),
                PlanDecision(kind="final", answer="done"),
            ]
        )

    spec = task(allowed_tools=frozenset({"write"}))
    with ThreadPoolExecutor(max_workers=1) as pool:
        first_future = pool.submit(agent.run, plan(), spec, user(), approval=lambda *_: True)
        assert started.wait(timeout=1)
        duplicate = agent.run(plan(), spec, user(), approval=lambda *_: True)
        release.set()
        first = first_future.result(timeout=1)

    assert first.status == "succeeded"
    assert duplicate.error_code == "IDEMPOTENCY_IN_PROGRESS"
    assert calls == 1


def test_planner_cannot_mutate_runtime_allowlist_or_existing_observations():
    class MutatingPlanner:
        calls = 0

        def decide(self, received_task, received_observations, tool_schemas):
            del tool_schemas
            self.calls += 1
            # 这些对象只是运行时快照的深拷贝；修改它们不能扩大真实权限或污染审计结果。
            received_task.allowed_tools = frozenset({"query_metric", "write"})
            if received_observations:
                received_observations[0].data["rows"][0]["value"] = 0.01
            return PlanDecision(kind="tool", tool_name="write", arguments={})

    planner = MutatingPlanner()
    original = task()
    result = harness().run(planner, original, user("metrics:query"))
    assert result.error_code == "TOOL_NOT_ALLOWED"
    assert original.allowed_tools == frozenset({"query_metric"})


def test_constructed_invalid_planner_and_verifier_objects_are_revalidated():
    class ConstructedPlanner:
        def decide(self, task, observations, tool_schemas):
            del task, observations, tool_schemas
            return PlanDecision.model_construct(kind="tool", tool_name=None, arguments={})

    planner_result = harness().run(ConstructedPlanner(), task(), user("metrics:query"))

    def constructed_verifier(task, answer, observations):
        del task, answer, observations
        return Verification.model_construct(passed="yes", code=123, message=None)

    verifier_result = AgentHarness(build_demo_registry(), constructed_verifier).run(
        successful_planner(), task(), user("metrics:query")
    )
    assert planner_result.error_code == "PLANNER_CONTRACT_INVALID"
    assert verifier_result.error_code == "VERIFIER_CONTRACT_INVALID"


def test_verifier_rejects_non_array_rows_with_stable_schema_error():
    verification = verify_metric_answer(
        task(),
        "昨日成功率为 98%。",
        [Observation(tool_name="query_metric", status="ok", data={"rows": None})],
    )
    # None 表示没有结果；非数组对象则是协议错误。
    assert verification.code == "EMPTY_RESULT"
    malformed = verify_metric_answer(
        task(),
        "昨日成功率为 98%。",
        [Observation(tool_name="query_metric", status="ok", data={"rows": {"value": 0.98}})],
    )
    assert malformed.code == "RESULT_SCHEMA_INVALID"


def test_verifier_binds_rows_to_declared_metric_and_requires_every_value():
    wrong_metric = verify_metric_answer(
        task(),
        "昨日成功率为 98%。",
        [
            Observation(
                tool_name="query_metric",
                status="ok",
                data={"rows": [{"metric": "revenue", "value": 0.98}]},
            )
        ],
    )
    partial_answer = verify_metric_answer(
        task(),
        "两个时段成功率分别为 98%。",
        [
            Observation(
                tool_name="query_metric",
                status="ok",
                data={
                    "rows": [
                        {"metric": "success_rate", "value": 0.98},
                        {"metric": "success_rate", "value": 0.91},
                    ]
                },
            )
        ],
    )
    missing_target = verify_metric_answer(
        task(expected_metric=None),
        "昨日成功率为 98%。",
        [
            Observation(
                tool_name="query_metric",
                status="ok",
                data={"rows": [{"metric": "success_rate", "value": 0.98}]},
            )
        ],
    )
    assert wrong_metric.code == "METRIC_MISMATCH"
    assert partial_answer.code == "ANSWER_MISMATCH"
    assert missing_target.code == "VERIFICATION_TARGET_MISSING"


def test_cancel_check_failure_and_cancellation_during_verifier_are_stable_results():
    crashing = harness().run(
        successful_planner(),
        task(),
        user("metrics:query"),
        cancelled=lambda: (_ for _ in ()).throw(RuntimeError("cancel source unavailable")),
    )

    cancel_now = Event()

    def cancelling_verifier(task, answer, observations):
        del task, answer, observations
        cancel_now.set()
        return Verification(passed=True, code="OK", message="ok")

    cancelled_result = AgentHarness(build_demo_registry(), cancelling_verifier).run(
        successful_planner(),
        task(),
        user("metrics:query"),
        cancelled=cancel_now.is_set,
    )
    assert crashing.status == "failed"
    assert crashing.error_code == "CANCEL_CHECK_ERROR"
    assert cancelled_result.status == "cancelled"
    assert cancelled_result.error_code == "USER_CANCELLED"


def test_tool_registry_rejects_missing_guard_fields_and_non_finite_timeout():
    class Args(BaseModel):
        value: str

    with pytest.raises(ValueError, match="tenant_argument"):
        ToolSpec(
            name="bad-tenant",
            description="bad",
            args_model=Args,
            handler=lambda _: None,
            tenant_argument="tenant_typo",
        )
    with pytest.raises(ValueError, match="idempotency_field"):
        ToolSpec(
            name="bad-idempotency",
            description="bad",
            args_model=Args,
            handler=lambda _: None,
            has_side_effect=True,
            idempotency_field="request_typo",
        )
    with pytest.raises(ValueError, match="timeout_seconds"):
        ToolSpec(
            name="bad-timeout",
            description="bad",
            args_model=Args,
            handler=lambda _: None,
            timeout_seconds=float("nan"),
        )


def test_cancel_check_timeout_and_invalid_return_do_not_hang_or_coerce_truthiness():
    def slow_cancel():
        time.sleep(0.03)
        return False

    timed_out = harness().run(
        successful_planner(),
        task(cancel_check_timeout_seconds=0.001),
        user("metrics:query"),
        cancelled=slow_cancel,
    )
    invalid = harness().run(
        successful_planner(),
        task(),
        user("metrics:query"),
        cancelled=lambda: "false",
    )
    assert timed_out.error_code == "CANCEL_CHECK_TIMEOUT"
    assert invalid.error_code == "CANCEL_CHECK_CONTRACT_INVALID"
