"""阶段 B：使用官方 A2A SDK 1.x 建立可追踪、幂等的报告 Agent 服务。"""

import asyncio
import inspect
import math
import re
from collections.abc import Awaitable, Callable

import uvicorn
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.context import ServerCallContext
from a2a.server.routes.agent_card_routes import create_agent_card_routes
from a2a.server.routes.common import DefaultServerCallContextBuilder
from a2a.server.routes.rest_routes import create_rest_routes
from a2a.server.tasks import InMemoryTaskStore, TaskUpdater
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentInterface,
    AgentSkill,
    Part,
    Task,
    TaskState,
    TaskStatus,
)
from starlette.applications import Starlette

from a2a_lab.execution import ExecutionError, ReportExecutionLedger


REPORT_SKILL = AgentSkill(
    id="generate-management-report",
    name="Generate management report",
    description="Turn an aggregated metric summary into a short Markdown report.",
    tags=["report", "analytics", "markdown"],
    examples=["Generate a report from revenue and success-rate aggregates."],
    input_modes=["text/plain"],
    output_modes=["text/markdown"],
)

AGENT_CARD = AgentCard(
    name="Report Agent",
    description="Creates reports from already aggregated, non-sensitive metrics.",
    supported_interfaces=[
        AgentInterface(
            url="http://127.0.0.1:9009/a2a",
            protocol_binding="HTTP+JSON",
            protocol_version="1.0",
        )
    ],
    version="0.2.0",
    capabilities=AgentCapabilities(streaming=True, push_notifications=False),
    default_input_modes=["text/plain"],
    default_output_modes=["text/markdown"],
    skills=[REPORT_SKILL],
)


class ReportAgentExecutor(AgentExecutor):
    """A2A 协议 Executor；真实模型仅替换 report_generator。"""

    def __init__(
        self,
        report_generator: Callable[[str], str | Awaitable[str]] | None = None,
        *,
        ledger: ReportExecutionLedger | None = None,
        generation_timeout_seconds: float = 5.0,
    ) -> None:
        if not math.isfinite(generation_timeout_seconds) or generation_timeout_seconds <= 0:
            raise ValueError("generation_timeout_seconds 必须是大于 0 的有限数")
        self._report_generator = report_generator or _render_report
        self.ledger = ledger or ReportExecutionLedger()
        self._generation_timeout_seconds = generation_timeout_seconds
        self._protocol_task_to_execution: dict[str, str] = {}

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)
        user_input = context.get_user_input()
        await event_queue.enqueue_event(
            Task(
                id=context.task_id,
                context_id=context.context_id,
                status=TaskStatus(state=TaskState.TASK_STATE_SUBMITTED),
                history=[context.message],
            )
        )
        if context.tenant != "tenant-a":
            await updater.reject(updater.new_agent_message([Part(text="租户无权委托该 Agent")]))
            return
        if not user_input.strip() or len(user_input) > 4_000:
            await updater.reject(updater.new_agent_message([Part(text="输入为空或超过长度限制")]))
            return

        metadata = context.metadata or {}
        trace_id = metadata.get("traceId", context.task_id)
        idempotency_key = metadata.get("idempotencyKey", context.task_id)
        if not _valid_metadata_value(trace_id) or not _valid_metadata_value(idempotency_key):
            await updater.reject(
                updater.new_agent_message(
                    [Part(text="INVALID_METADATA: traceId/idempotencyKey 必须是 1～100 字符的字符串")]
                )
            )
            return
        try:
            claim = self.ledger.claim(
                tenant=context.tenant,
                idempotency_key=idempotency_key,
                summary=user_input,
                trace_id=trace_id,
            )
        except ExecutionError as exc:
            await updater.reject(updater.new_agent_message([Part(text=f"{exc.code}: {exc.message}")]))
            return
        self._protocol_task_to_execution[context.task_id] = claim.record.id

        if claim.replayed:
            if claim.record.state == "completed" and claim.record.report:
                await updater.start_work(updater.new_agent_message([Part(text="命中幂等执行结果")]))
                await updater.add_artifact(
                    [Part(text=claim.record.report)],
                    name="management-report.md",
                    metadata={
                        "trace_id": trace_id,
                        "execution_id": claim.record.id,
                        "idempotency_key": idempotency_key,
                        "replayed": True,
                    },
                )
                await updater.complete(updater.new_agent_message([Part(text="返回已完成报告")]))
            else:
                await updater.reject(
                    updater.new_agent_message([Part(text=f"相同委托已处于 {claim.record.state} 状态")])
                )
            return

        if _contains_sensitive_data(user_input):
            self.ledger.reject(claim.record.id, "SENSITIVE_INPUT")
            await updater.reject(updater.new_agent_message([Part(text="输入包含可能的明细或敏感信息")]))
            return

        self.ledger.start(claim.record.id)
        await updater.start_work(updater.new_agent_message([Part(text="正在生成报告")]))
        try:
            report = await asyncio.wait_for(
                self._generate(user_input), timeout=self._generation_timeout_seconds
            )
            if not report.strip() or len(report) > 20_000:
                raise ValueError("empty or oversized report")
        except TimeoutError:
            self.ledger.fail(claim.record.id, "GENERATION_TIMEOUT")
            await updater.failed(updater.new_agent_message([Part(text="报告生成超时")]))
            return
        except Exception as exc:
            self.ledger.fail(claim.record.id, "GENERATION_FAILED")
            await updater.failed(
                updater.new_agent_message([Part(text=f"报告生成失败：{type(exc).__name__}")])
            )
            return

        completed = self.ledger.complete(claim.record.id, report)
        await updater.add_artifact(
            [Part(text=report)],
            name="management-report.md",
            metadata={
                "trace_id": trace_id,
                "execution_id": completed.id,
                "idempotency_key": idempotency_key,
                "replayed": False,
            },
        )
        await updater.complete(updater.new_agent_message([Part(text="报告生成完成")]))

    async def _generate(self, user_input: str) -> str:
        if inspect.iscoroutinefunction(self._report_generator):
            report = await self._report_generator(user_input)
        else:
            # 同步生成器放入线程，避免阻塞 A2A Server 的事件循环。
            report = await asyncio.to_thread(self._report_generator, user_input)
        if inspect.isawaitable(report):
            report = await report
        if not isinstance(report, str):
            raise TypeError("report_generator must return str")
        return report

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)
        execution_id = self._protocol_task_to_execution.get(context.task_id)
        if execution_id:
            try:
                self.ledger.cancel(execution_id)
            except ExecutionError:
                # 若业务账本已经进入终态，取消不能反向覆盖 completed/failed/rejected。
                # SDK 会等待正在完成的 execute 流程写入对应协议终态。
                return
        await updater.cancel(updater.new_agent_message([Part(text="任务已取消")]))


class TenantContextBuilder(DefaultServerCallContextBuilder):
    """教学用身份适配：从可信网关头读取租户，而不是相信请求正文。"""

    def build(self, request) -> ServerCallContext:
        base = super().build(request)
        return base.model_copy(update={"tenant": request.headers.get("x-tenant", "")})


def _contains_sensitive_data(text: str) -> bool:
    return bool(
        re.search(
            r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}"
            r"|\b1\d{10}\b"
            r"|(?i:\bBearer\s+[A-Za-z0-9._~+/=-]+)"
            r"|\bsk-[A-Za-z0-9_-]{8,}\b"
            r"|(?i:\b(?:api[_ -]?key|authorization)\s*[:=]\s*[A-Za-z0-9._~+/-]{8,})",
            text,
        )
    )


def _valid_metadata_value(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip()) and len(value) <= 100


def _render_report(summary: str) -> str:
    return f"# 管理报告\n\n## 数据摘要\n\n{summary}\n\n## 结论\n\n请结合目标与历史基线进一步解释变化。"


def build_a2a_app(
    report_generator: Callable[[str], str | Awaitable[str]] | None = None,
    *,
    ledger: ReportExecutionLedger | None = None,
    generation_timeout_seconds: float = 5.0,
) -> Starlette:
    executor = ReportAgentExecutor(
        report_generator,
        ledger=ledger,
        generation_timeout_seconds=generation_timeout_seconds,
    )
    handler = DefaultRequestHandler(
        agent_executor=executor,
        task_store=InMemoryTaskStore(),
        agent_card=AGENT_CARD,
    )
    app = Starlette(
        routes=[
            *create_agent_card_routes(AGENT_CARD),
            *create_rest_routes(
                handler,
                context_builder=TenantContextBuilder(),
                path_prefix="/a2a",
            ),
        ]
    )
    # 测试和教学 demo 可观察业务执行事件；不要把可变账本作为公开 HTTP API。
    app.state.execution_ledger = executor.ledger
    return app


a2a_app = build_a2a_app()


def main() -> None:
    uvicorn.run(a2a_app, host="127.0.0.1", port=9009)


if __name__ == "__main__":
    main()
