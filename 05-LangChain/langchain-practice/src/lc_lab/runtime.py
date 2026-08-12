"""在 LangChain Agent 外增加输入边界、停止条件和可审计结果。"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from time import perf_counter
from typing import Literal

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langgraph.errors import GraphRecursionError
from pydantic import BaseModel, ConfigDict, Field

from lc_lab.agent import build_agent
from lc_lab.domain import (
    DEFAULT_CATALOG,
    DEFAULT_CONTEXT,
    MetricCatalog,
    MetricPermissionError,
    UserContext,
)
from lc_lab.tools import ToolBudgetExceeded, ToolCallBudget


class RuntimeModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AgentPolicy(RuntimeModel):
    max_question_chars: int = Field(default=500, ge=1, le=10_000)
    recursion_limit: int = Field(default=12, ge=2, le=100)
    max_tool_calls: int = Field(default=3, ge=1, le=20)
    wall_clock_timeout_seconds: float = Field(default=5.0, gt=0, le=120)


class TaskContract(RuntimeModel):
    """业务任务的完成条件，不能把“模型说完了”误判为“任务完成了”。"""

    required_tools: frozenset[str] = frozenset({"get_metric_definition"})
    min_successful_tool_results: int = Field(default=1, ge=0, le=20)


class AuditEvent(RuntimeModel):
    sequence: int = Field(ge=1)
    kind: Literal["model", "tool_call", "tool_result", "runtime_error", "contract_error"]
    name: str
    detail: str = ""


class AgentRun(RuntimeModel):
    status: Literal["completed", "rejected", "failed"]
    answer: str
    tool_calls: int = Field(ge=0)
    successful_tool_results: int = Field(default=0, ge=0)
    elapsed_ms: float = Field(ge=0)
    events: list[AuditEvent]
    error_code: str | None = None


def _safe_detail(value: object, *, limit: int = 160) -> str:
    text = str(value).replace("admin_secret", "[REDACTED_METRIC]")
    return text if len(text) <= limit else text[:limit] + "…"


def _events(
    messages: list[BaseMessage],
) -> tuple[list[AuditEvent], int, set[str], int]:
    events: list[AuditEvent] = []
    tool_calls = 0
    successful_tool_names: set[str] = set()
    successful_tool_results = 0
    for message in messages:
        if isinstance(message, AIMessage):
            if message.tool_calls:
                for call in message.tool_calls:
                    tool_calls += 1
                    events.append(
                        AuditEvent(
                            sequence=len(events) + 1,
                            kind="tool_call",
                            name=call["name"],
                            detail=_safe_detail(call.get("args", {})),
                        )
                    )
            elif message.content:
                events.append(
                    AuditEvent(
                        sequence=len(events) + 1,
                        kind="model",
                        name="final_answer",
                        detail=_safe_detail(message.content),
                    )
                )
        elif isinstance(message, ToolMessage):
            status = getattr(message, "status", "success")
            if status != "error" and str(message.content).strip():
                successful_tool_results += 1
                if message.name:
                    successful_tool_names.add(message.name)
            events.append(
                AuditEvent(
                    sequence=len(events) + 1,
                    kind="tool_result",
                    name=message.name or "unknown_tool",
                    detail=_safe_detail(f"status={status}; {message.content}"),
                )
            )
    return events, tool_calls, successful_tool_names, successful_tool_results


def _invoke_with_deadline(agent, payload: dict, *, timeout_seconds: float, recursion_limit: int):
    """给整个 model→tool 循环设置 wall-clock 上限。

    Python 线程无法安全强杀；超时后立即向调用方返回，且本练习工具保持只读。生产系统应
    同时把 deadline 传给模型 HTTP 客户端和工具客户端，让底层请求也能真正取消。
    """

    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="metric-agent")
    future = executor.submit(
        agent.invoke,
        payload,
        {"recursion_limit": recursion_limit},
    )
    try:
        return future.result(timeout=timeout_seconds)
    except FutureTimeoutError:
        future.cancel()
        raise
    finally:
        # wait=False 保证 wall-clock 边界真实生效；只读工具避免超时后产生未知副作用。
        executor.shutdown(wait=False, cancel_futures=True)


def run_metric_agent(
    question: str,
    *,
    model: BaseChatModel | None = None,
    context: UserContext = DEFAULT_CONTEXT,
    catalog: MetricCatalog = DEFAULT_CATALOG,
    policy: AgentPolicy | None = None,
    contract: TaskContract | None = None,
) -> AgentRun:
    policy = policy or AgentPolicy()
    contract = contract or TaskContract()
    normalized = question.strip()
    if not normalized or len(normalized) > policy.max_question_chars:
        return AgentRun(
            status="rejected",
            answer="问题为空或过长，未调用模型。",
            tool_calls=0,
            elapsed_ms=0,
            events=[],
            error_code="INVALID_INPUT",
        )

    started = perf_counter()
    budget = ToolCallBudget(policy.max_tool_calls)
    try:
        agent = build_agent(
            model=model,
            context=context,
            catalog=catalog,
            tool_budget=budget,
        )
        result = _invoke_with_deadline(
            agent,
            {"messages": [{"role": "user", "content": normalized}]},
            timeout_seconds=policy.wall_clock_timeout_seconds,
            recursion_limit=policy.recursion_limit,
        )
        messages = result["messages"]
        events, tool_calls, successful_tools, successful_tool_results = _events(messages)
        if tool_calls > policy.max_tool_calls:
            return AgentRun(
                status="failed",
                answer="工具调用次数超过策略上限。",
                tool_calls=tool_calls,
                successful_tool_results=successful_tool_results,
                elapsed_ms=(perf_counter() - started) * 1000,
                events=events,
                error_code="TOOL_BUDGET_EXCEEDED",
            )
        missing_tools = sorted(contract.required_tools - successful_tools)
        if missing_tools or successful_tool_results < contract.min_successful_tool_results:
            detail = (
                f"missing_tools={missing_tools}; successful_results={successful_tool_results}; "
                f"required_results={contract.min_successful_tool_results}"
            )
            events.append(
                AuditEvent(
                    sequence=len(events) + 1,
                    kind="contract_error",
                    name="TASK_CONTRACT_UNSATISFIED",
                    detail=detail,
                )
            )
            return AgentRun(
                status="failed",
                answer="任务未获得所需的工具证据。",
                tool_calls=tool_calls,
                successful_tool_results=successful_tool_results,
                elapsed_ms=(perf_counter() - started) * 1000,
                events=events,
                error_code="REQUIRED_TOOL_EVIDENCE_MISSING",
            )
        return AgentRun(
            status="completed",
            answer=str(messages[-1].content),
            tool_calls=tool_calls,
            successful_tool_results=successful_tool_results,
            elapsed_ms=(perf_counter() - started) * 1000,
            events=events,
        )
    except FutureTimeoutError:
        error_code = "AGENT_TIMEOUT"
        detail = f"model/tool loop exceeded {policy.wall_clock_timeout_seconds}s"
    except MetricPermissionError as exc:
        error_code = "PERMISSION_DENIED"
        detail = _safe_detail(exc)
    except ToolBudgetExceeded as exc:
        error_code = "TOOL_BUDGET_EXCEEDED"
        detail = _safe_detail(exc)
    except GraphRecursionError as exc:
        error_code = "RECURSION_LIMIT"
        detail = _safe_detail(exc)
    except Exception as exc:  # 适配层统一错误形状，原异常类型仍保留在 trace 中。
        error_code = "AGENT_RUNTIME_ERROR"
        detail = _safe_detail(f"{type(exc).__name__}: {exc}")
    return AgentRun(
        status="failed",
        answer="请求处理失败。",
        tool_calls=budget.used,
        elapsed_ms=(perf_counter() - started) * 1000,
        events=[AuditEvent(sequence=1, kind="runtime_error", name=error_code, detail=detail)],
        error_code=error_code,
    )
