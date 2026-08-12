from __future__ import annotations

import json
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Literal
from uuid import uuid4

from pydantic import ValidationError

from .errors import HarnessError
from .idempotency import InMemoryIdempotencyStore
from .models import Observation, PlanDecision, RunResult, TaskSpec, UserContext, Verification
from .planner import Planner
from .registry import ToolRegistry, ToolSpec
from .trace import TraceRecorder


Verifier = Callable[[TaskSpec, str, list[Observation]], Verification]
Approval = Callable[[str, dict[str, Any]], bool]
CancelCheck = Callable[[], bool]


@dataclass(frozen=True)
class ToolOutcome:
    observation: Observation | None = None
    cost_units: int = 0
    terminal_status: Literal["failed", "cancelled", "waiting_approval"] | None = None
    error_code: str | None = None


class AgentHarness:
    def __init__(
        self,
        registry: ToolRegistry,
        verifier: Verifier,
        *,
        idempotency_store: InMemoryIdempotencyStore | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ):
        self.registry = registry
        self.verifier = verifier
        self.idempotency_store = idempotency_store or InMemoryIdempotencyStore()
        self.clock = clock
        self.sleeper = sleeper

    def run(
        self,
        planner: Planner,
        task: TaskSpec,
        user: UserContext,
        *,
        approval: Approval | None = None,
        cancelled: CancelCheck | None = None,
    ) -> RunResult:
        # 对调用方对象做一次经验证的深快照。Planner 在另一个线程中运行，不能让它（或调用方
        # 的并发修改）改变本次运行的 allowlist、预算、租户等安全边界。
        task = TaskSpec.model_validate(task.model_dump(mode="python"))
        user = UserContext.model_validate(user.model_dump(mode="python"))
        run_id = uuid4().hex
        trace = TraceRecorder()
        observations: list[Observation] = []
        cost = 0
        deadline = self.clock() + task.deadline_seconds
        trace.add("task_started", run_id=run_id, task_id=task.task_id, user_id=user.user_id, tenant=user.tenant)

        seen_calls: set[str] = set()
        planner_retries = 0
        for step in range(1, task.max_steps + 1):
            interrupted = self._interrupt(cancelled, deadline, task.cancel_check_timeout_seconds)
            if interrupted:
                status, code = interrupted
                trace.add("task_interrupted", "error", code=code)
                return self._finish(run_id, task, status, step - 1, cost, observations, trace, error_code=code)

            tool_schemas = self.registry.schemas(task.allowed_tools)
            payload_chars = self._planner_payload_chars(task, observations, tool_schemas)
            # 上下文预算必须覆盖真正送给 Planner 的三部分，不能只检查初始问题。
            # 否则多轮工具 observation 会逐步把模型上下文撑爆。
            if payload_chars > task.max_context_chars:
                trace.add(
                    "context_rejected",
                    "error",
                    code="CONTEXT_BUDGET_EXCEEDED",
                    actual_chars=payload_chars,
                    limit_chars=task.max_context_chars,
                )
                return self._finish(
                    run_id,
                    task,
                    "failed",
                    step - 1,
                    cost,
                    observations,
                    trace,
                    error_code="CONTEXT_BUDGET_EXCEEDED",
                )

            # 每次 Planner 推理也消耗预算；否则模型超时重试可以绕过总成本上限。
            if cost + 1 > task.max_cost_units:
                trace.add("budget_exhausted", "error", budget="cost")
                return self._finish(run_id, task, "failed", step - 1, cost, observations, trace, error_code="COST_BUDGET_EXCEEDED")
            cost += 1
            try:
                raw_decision = self._with_timeout(
                    lambda: planner.decide(
                        task.model_copy(deep=True),
                        [item.model_copy(deep=True) for item in observations],
                        deepcopy(tool_schemas),
                    ),
                    min(task.planner_timeout_seconds, self._remaining(deadline)),
                )
                # Pydantic 对同类实例默认会直接信任；先 dump 再 validate，防止
                # model_construct() 制造出的非法对象绕过运行时契约。
                decision_payload = (
                    raw_decision.model_dump(mode="python", warnings=False)
                    if isinstance(raw_decision, PlanDecision)
                    else raw_decision
                )
                decision = PlanDecision.model_validate(decision_payload)
                planner_retries = 0
            except FutureTimeoutError:
                if self._remaining(deadline) <= 0.001:
                    trace.add("planner_failed", "error", code="TASK_DEADLINE_EXCEEDED")
                    return self._finish(run_id, task, "failed", step, cost, observations, trace, error_code="TASK_DEADLINE_EXCEEDED")
                if planner_retries < task.max_transient_retries:
                    planner_retries += 1
                    self._backoff(task, planner_retries, deadline)
                    trace.add("planner_retry", "pending", code="MODEL_TIMEOUT", retry=planner_retries)
                    continue
                trace.add("planner_failed", "error", code="MODEL_TIMEOUT")
                return self._finish(run_id, task, "failed", step, cost, observations, trace, error_code="MODEL_TIMEOUT")
            except ValidationError as exc:
                fields = [".".join(map(str, error["loc"])) for error in exc.errors()]
                trace.add("planner_failed", "error", code="PLANNER_CONTRACT_INVALID", fields=fields)
                return self._finish(run_id, task, "failed", step, cost, observations, trace, error_code="PLANNER_CONTRACT_INVALID")
            except Exception as exc:
                trace.add("planner_failed", "error", code="MODEL_ERROR", error_type=type(exc).__name__)
                return self._finish(run_id, task, "failed", step, cost, observations, trace, error_code="MODEL_ERROR")

            trace.add("planner_decision", kind=decision.kind, tool_name=decision.tool_name)
            if decision.kind == "final":
                interrupted = self._interrupt(cancelled, deadline, task.cancel_check_timeout_seconds)
                if interrupted:
                    status, code = interrupted
                    trace.add("task_interrupted", "error", code=code, phase="before_verifier")
                    return self._finish(run_id, task, status, step, cost, observations, trace, error_code=code)
                try:
                    raw_verification = self._with_timeout(
                        lambda: self.verifier(
                            task.model_copy(deep=True),
                            decision.answer or "",
                            [item.model_copy(deep=True) for item in observations],
                        ),
                        min(task.verifier_timeout_seconds, self._remaining(deadline)),
                    )
                    verification_payload = (
                        raw_verification.model_dump(mode="python", warnings=False)
                        if isinstance(raw_verification, Verification)
                        else raw_verification
                    )
                    verification = Verification.model_validate(verification_payload)
                    interrupted = self._interrupt(cancelled, deadline, task.cancel_check_timeout_seconds)
                    if interrupted:
                        status, code = interrupted
                        trace.add("verification", "error", code=code)
                        return self._finish(
                            run_id,
                            task,
                            status,
                            step,
                            cost,
                            observations,
                            trace,
                            error_code=code,
                        )
                except FutureTimeoutError:
                    code = "TASK_DEADLINE_EXCEEDED" if self._remaining(deadline) <= 0.001 else "VERIFIER_TIMEOUT"
                    trace.add("verification", "error", code=code)
                    return self._finish(run_id, task, "failed", step, cost, observations, trace, error_code=code)
                except ValidationError as exc:
                    fields = [".".join(map(str, error["loc"])) for error in exc.errors()]
                    trace.add("verification", "error", code="VERIFIER_CONTRACT_INVALID", fields=fields)
                    return self._finish(
                        run_id,
                        task,
                        "failed",
                        step,
                        cost,
                        observations,
                        trace,
                        error_code="VERIFIER_CONTRACT_INVALID",
                    )
                except Exception as exc:
                    trace.add("verification", "error", code="VERIFIER_ERROR", error_type=type(exc).__name__)
                    return self._finish(run_id, task, "failed", step, cost, observations, trace, error_code="VERIFIER_ERROR")
                trace.add("verification", "ok" if verification.passed else "error", **verification.model_dump())
                if verification.passed:
                    return self._finish(run_id, task, "succeeded", step, cost, observations, trace, answer=decision.answer)
                return self._finish(run_id, task, "failed", step, cost, observations, trace, error_code=verification.code)

            outcome = self._run_tool(
                decision.tool_name or "",
                decision.arguments,
                task,
                user,
                approval,
                cancelled,
                deadline,
                task.max_cost_units - cost,
                seen_calls,
                trace,
            )
            cost += outcome.cost_units
            if outcome.terminal_status:
                return self._finish(
                    run_id,
                    task,
                    outcome.terminal_status,
                    step,
                    cost,
                    observations,
                    trace,
                    error_code=outcome.error_code,
                )
            if outcome.observation is not None:
                observations.append(outcome.observation)

        trace.add("budget_exhausted", "error", budget="steps")
        return self._finish(run_id, task, "failed", task.max_steps, cost, observations, trace, error_code="MAX_STEPS_EXCEEDED")

    def _run_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        task: TaskSpec,
        user: UserContext,
        approval: Approval | None,
        cancelled: CancelCheck | None,
        deadline: float,
        available_cost: int,
        seen_calls: set[str],
        trace: TraceRecorder,
    ) -> ToolOutcome:
        if name not in task.allowed_tools:
            trace.add("tool_rejected", "error", code="TOOL_NOT_ALLOWED", tool_name=name)
            return ToolOutcome(terminal_status="failed", error_code="TOOL_NOT_ALLOWED")
        spec = self.registry.get(name)
        if spec is None:
            trace.add("tool_rejected", "error", code="UNKNOWN_TOOL", tool_name=name)
            return ToolOutcome(terminal_status="failed", error_code="UNKNOWN_TOOL")
        if spec.required_permission and spec.required_permission not in user.permissions:
            trace.add("tool_rejected", "error", code="PERMISSION_DENIED", tool_name=name)
            return ToolOutcome(terminal_status="failed", error_code="PERMISSION_DENIED")
        try:
            parsed = spec.args_model.model_validate(arguments)
        except ValidationError as exc:
            fields = [".".join(map(str, error["loc"])) for error in exc.errors()]
            trace.add("tool_rejected", "error", code="INVALID_ARGUMENTS", fields=fields)
            return ToolOutcome(terminal_status="failed", error_code="INVALID_ARGUMENTS")

        canonical_arguments = parsed.model_dump(mode="json")
        if spec.tenant_argument:
            requested_tenant = canonical_arguments.get(spec.tenant_argument)
            # 身份作用域必须由 Harness 强制执行，不能相信模型生成的 tenant 参数。
            if requested_tenant != user.tenant:
                trace.add(
                    "tool_rejected",
                    "error",
                    code="TENANT_SCOPE_VIOLATION",
                    requested_tenant=requested_tenant,
                    user_tenant=user.tenant,
                )
                return ToolOutcome(terminal_status="failed", error_code="TENANT_SCOPE_VIOLATION")

        signature = f"{name}:{json.dumps(canonical_arguments, ensure_ascii=False, sort_keys=True)}"
        if signature in seen_calls:
            trace.add("tool_rejected", "error", code="REPEATED_TOOL_CALL", tool_name=name)
            return ToolOutcome(terminal_status="failed", error_code="REPEATED_TOOL_CALL")
        seen_calls.add(signature)

        idempotency_key = self._idempotency_key(spec, user, canonical_arguments)
        if idempotency_key:
            state, cached_data = self.idempotency_store.lookup(idempotency_key, signature)
            if state == "conflict":
                trace.add("tool_rejected", "error", code="IDEMPOTENCY_CONFLICT", tool_name=name)
                return ToolOutcome(terminal_status="failed", error_code="IDEMPOTENCY_CONFLICT")
            if state == "completed":
                trace.add("tool_replayed", tool_name=name, idempotency_key=idempotency_key)
                return ToolOutcome(observation=Observation(tool_name=name, status="ok", data=cached_data))
            if state == "in_progress":
                trace.add("tool_rejected", "error", code="IDEMPOTENCY_IN_PROGRESS", tool_name=name)
                return ToolOutcome(terminal_status="failed", error_code="IDEMPOTENCY_IN_PROGRESS")
            if state == "unknown":
                trace.add("tool_rejected", "error", code="SIDE_EFFECT_OUTCOME_UNKNOWN", tool_name=name)
                return ToolOutcome(terminal_status="failed", error_code="SIDE_EFFECT_OUTCOME_UNKNOWN")

        if spec.has_side_effect:
            if approval is None:
                trace.add("approval_required", "pending", tool_name=name, risk_level=spec.risk_level)
                return ToolOutcome(terminal_status="waiting_approval", error_code="APPROVAL_REQUIRED")
            try:
                # 审批函数只应做授权判断；这里给它独立超时，并继续受任务总 deadline 约束。
                approved = self._with_timeout(
                    lambda: approval(name, deepcopy(canonical_arguments)),
                    min(task.approval_timeout_seconds, self._remaining(deadline)),
                )
            except FutureTimeoutError:
                code = "TASK_DEADLINE_EXCEEDED" if self._remaining(deadline) <= 0.001 else "APPROVAL_TIMEOUT"
                trace.add("approval_failed", "error", tool_name=name, code=code)
                return ToolOutcome(terminal_status="failed", error_code=code)
            except Exception as exc:
                trace.add("approval_failed", "error", tool_name=name, code="APPROVAL_ERROR", error_type=type(exc).__name__)
                return ToolOutcome(terminal_status="failed", error_code="APPROVAL_ERROR")
            interrupted = self._interrupt(cancelled, deadline, task.cancel_check_timeout_seconds)
            if interrupted:
                status, code = interrupted
                trace.add("approval_failed", "error", tool_name=name, code=code)
                return ToolOutcome(terminal_status=status, error_code=code)
            if not isinstance(approved, bool):
                trace.add("approval_failed", "error", tool_name=name, code="APPROVAL_CONTRACT_INVALID")
                return ToolOutcome(terminal_status="failed", error_code="APPROVAL_CONTRACT_INVALID")
            if not approved:
                trace.add("approval_rejected", "error", tool_name=name)
                return ToolOutcome(terminal_status="cancelled", error_code="HUMAN_REJECTED")

        consumed_cost = 0
        for retry in range(task.max_transient_retries + 1):
            interrupted = self._interrupt(cancelled, deadline, task.cancel_check_timeout_seconds)
            if interrupted:
                status, code = interrupted
                trace.add("tool_interrupted", "error", tool_name=name, code=code)
                return ToolOutcome(cost_units=consumed_cost, terminal_status=status, error_code=code)
            # 工具每一次真实调用都计费，包含失败和重试，防止预算统计虚低。
            if consumed_cost + spec.cost_units > available_cost:
                trace.add("budget_exhausted", "error", budget="cost", tool_name=name)
                return ToolOutcome(cost_units=consumed_cost, terminal_status="failed", error_code="COST_BUDGET_EXCEEDED")

            if idempotency_key:
                state, cached_data = self.idempotency_store.reserve(idempotency_key, signature)
                if state == "conflict":
                    trace.add("tool_rejected", "error", code="IDEMPOTENCY_CONFLICT", tool_name=name)
                    return ToolOutcome(cost_units=consumed_cost, terminal_status="failed", error_code="IDEMPOTENCY_CONFLICT")
                if state == "completed":
                    trace.add("tool_replayed", tool_name=name, idempotency_key=idempotency_key)
                    return ToolOutcome(
                        observation=Observation(tool_name=name, status="ok", data=cached_data),
                        cost_units=consumed_cost,
                    )
                if state == "in_progress":
                    trace.add("tool_rejected", "error", code="IDEMPOTENCY_IN_PROGRESS", tool_name=name)
                    return ToolOutcome(cost_units=consumed_cost, terminal_status="failed", error_code="IDEMPOTENCY_IN_PROGRESS")
                if state == "unknown":
                    trace.add("tool_rejected", "error", code="SIDE_EFFECT_OUTCOME_UNKNOWN", tool_name=name)
                    return ToolOutcome(cost_units=consumed_cost, terminal_status="failed", error_code="SIDE_EFFECT_OUTCOME_UNKNOWN")

            consumed_cost += spec.cost_units
            try:
                started = self.clock()

                def invoke_tool() -> Any:
                    try:
                        result = spec.handler(parsed)
                        encoded_result = json.dumps(result, ensure_ascii=False, default=str)
                        if len(encoded_result) > spec.max_output_chars:
                            raise HarnessError("TOOL_OUTPUT_TOO_LARGE", "工具输出超过 Harness 限制")
                    except Exception:
                        if idempotency_key:
                            self.idempotency_store.mark_unknown(idempotency_key, signature)
                        raise
                    # complete 放在线程内部：即使调用方已超时，晚到结果仍会封存，避免再次执行。
                    if idempotency_key:
                        self.idempotency_store.complete(idempotency_key, signature, result)
                    return result

                data = self._with_timeout(
                    invoke_tool,
                    min(spec.timeout_seconds, self._remaining(deadline)),
                )
                duration_ms = round((self.clock() - started) * 1000, 3)
                if self.clock() >= deadline:
                    # handler 已明确返回时可以记录幂等结果，但任务仍不能越过总 deadline 宣告成功。
                    trace.add("tool_completed_after_deadline", "error", tool_name=name, code="TASK_DEADLINE_EXCEEDED")
                    return ToolOutcome(
                        cost_units=consumed_cost,
                        terminal_status="failed",
                        error_code="TASK_DEADLINE_EXCEEDED",
                    )
                trace.add(
                    "tool_completed",
                    tool_name=name,
                    tool_version=spec.version,
                    retry=retry,
                    duration_ms=duration_ms,
                    output=data,
                )
                return ToolOutcome(
                    observation=Observation(tool_name=name, status="ok", data=data),
                    cost_units=consumed_cost,
                )
            except FutureTimeoutError:
                if spec.has_side_effect:
                    # Python 线程超时不会终止 handler。即使带请求 ID，此时也不知道远端是否已写入，
                    # 因而绝不能在同一进程里贸然发起第二次调用。
                    trace.add(
                        "tool_failed",
                        "error",
                        tool_name=name,
                        code="SIDE_EFFECT_OUTCOME_UNKNOWN",
                        cause="TASK_DEADLINE_EXCEEDED" if self.clock() >= deadline else "TOOL_TIMEOUT",
                    )
                    return ToolOutcome(
                        cost_units=consumed_cost,
                        terminal_status="failed",
                        error_code="SIDE_EFFECT_OUTCOME_UNKNOWN",
                    )
                if self.clock() >= deadline:
                    error = HarnessError("TASK_DEADLINE_EXCEEDED", "任务总时限已到")
                else:
                    error = HarnessError("TOOL_TIMEOUT", "工具执行超时", retryable=True)
            except HarnessError as exc:
                error = exc
            except Exception as exc:
                error = HarnessError("TOOL_EXECUTION_ERROR", type(exc).__name__)

            if spec.has_side_effect:
                # 一旦副作用 handler 开始运行，异常本身不能证明远端没有写入。
                # 带幂等键的请求会被封存为 unknown；无幂等键的瞬时错误也禁止重试。
                code = "SIDE_EFFECT_OUTCOME_UNKNOWN" if idempotency_key or not error.retryable else "UNSAFE_RETRY_BLOCKED"
                trace.add("tool_failed", "error", tool_name=name, code=code, cause=error.code)
                return ToolOutcome(cost_units=consumed_cost, terminal_status="failed", error_code=code)

            if error.retryable and retry < task.max_transient_retries:
                self._backoff(task, retry + 1, deadline)
                trace.add("tool_retry", "pending", tool_name=name, code=error.code, retry=retry + 1)
                continue
            trace.add("tool_failed", "error", tool_name=name, code=error.code)
            return ToolOutcome(cost_units=consumed_cost, terminal_status="failed", error_code=error.code)
        raise AssertionError("unreachable")

    @staticmethod
    def _idempotency_key(spec: ToolSpec, user: UserContext, arguments: dict[str, Any]) -> str | None:
        if not spec.idempotency_field:
            return None
        value = arguments.get(spec.idempotency_field)
        if not isinstance(value, str) or not value.strip():
            return None
        return f"{user.tenant}:{spec.name}:{value}"

    def _interrupt(
        self,
        cancelled: CancelCheck | None,
        deadline: float,
        check_timeout_seconds: float,
    ) -> tuple[Literal["cancelled", "failed"], str] | None:
        if cancelled is not None:
            try:
                is_cancelled = self._with_timeout(
                    cancelled,
                    min(check_timeout_seconds, self._remaining(deadline)),
                )
                if not isinstance(is_cancelled, bool):
                    return "failed", "CANCEL_CHECK_CONTRACT_INVALID"
                if is_cancelled:
                    return "cancelled", "USER_CANCELLED"
            except FutureTimeoutError:
                return (
                    ("failed", "TASK_DEADLINE_EXCEEDED")
                    if self._remaining(deadline) <= 0.001
                    else ("failed", "CANCEL_CHECK_TIMEOUT")
                )
            except Exception:
                # 取消源通常来自事件总线/数据库；它失败时不能让异常击穿 Harness。
                return "failed", "CANCEL_CHECK_ERROR"
        if self.clock() >= deadline:
            return "failed", "TASK_DEADLINE_EXCEEDED"
        return None

    def _remaining(self, deadline: float) -> float:
        return max(0.000_001, deadline - self.clock())

    def _backoff(self, task: TaskSpec, retry: int, deadline: float) -> None:
        delay = min(task.retry_backoff_seconds * (2 ** (retry - 1)), self._remaining(deadline))
        if delay > 0:
            self.sleeper(delay)

    @staticmethod
    def _planner_payload_chars(task: TaskSpec, observations: list[Observation], tool_schemas: list[dict]) -> int:
        """按可序列化输入计算 Planner 负载，便于教学观察多轮上下文增长。"""
        payload = {
            "task": task.model_dump(mode="json"),
            "observations": [item.model_dump(mode="json") for item in observations],
            "tool_schemas": tool_schemas,
        }
        return len(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str))

    @staticmethod
    def _with_timeout(callback: Callable[[], Any], timeout_seconds: float) -> Any:
        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(callback)
        try:
            return future.result(timeout=timeout_seconds)
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    @staticmethod
    def _finish(
        run_id: str,
        task: TaskSpec,
        status: Literal["succeeded", "failed", "cancelled", "waiting_approval"],
        steps: int,
        cost: int,
        observations: list[Observation],
        trace: TraceRecorder,
        *,
        answer: str | None = None,
        error_code: str | None = None,
    ) -> RunResult:
        return RunResult(
            run_id=run_id,
            task_id=task.task_id,
            status=status,
            answer=answer,
            error_code=error_code,
            steps=steps,
            cost_units=cost,
            observations=list(observations),
            trace=trace.events,
        )
