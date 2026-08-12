"""阶段 A：私有 HTTP 需要自行定义发现、幂等、状态、事件和错误契约。"""

import json
import math
from collections.abc import Callable

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictFloat,
    StrictInt,
    ValidationError,
    field_validator,
)
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from a2a_lab.lifecycle import LifecycleError, TaskLifecycleService


class CustomTaskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    summary: dict[str, StrictInt | StrictFloat] = Field(min_length=1, max_length=20)
    trace_id: str = Field(min_length=1, max_length=100)

    @field_validator("summary", mode="before")
    @classmethod
    def reject_non_json_numbers(cls, value: object) -> object:
        """先于 Pydantic 类型转换拒绝 bool/非有限数，领域层还会做第二次校验。"""

        if isinstance(value, dict):
            for number in value.values():
                if isinstance(number, bool):
                    raise ValueError("bool is not an aggregate number")
                if isinstance(number, float) and not math.isfinite(number):
                    raise ValueError("aggregate numbers must be finite")
        return value


TASK_SERVICE = TaskLifecycleService()
# 兼容学习时直接观察内存任务；业务代码应通过 TaskLifecycleService 访问。
TASKS = TASK_SERVICE.tasks


def _identity(request: Request) -> tuple[str, set[str]]:
    tenant = request.headers.get("x-tenant", "")
    scopes = set(request.headers.get("x-scopes", "").split())
    return tenant, scopes


def _require_scope(scopes: set[str], scope: str) -> JSONResponse | None:
    if scope not in scopes:
        return JSONResponse({"code": "FORBIDDEN", "message": f"缺少 {scope} 权限"}, status_code=403)
    return None


async def list_agents(_request: Request) -> JSONResponse:
    # 自定义接口中这些字段、版本和 URL 都要由双方另行约定。
    return JSONResponse(
        {
            "agents": [
                {
                    "id": "report-agent",
                    "version": "0.2.0",
                    "capabilities": ["generate-report"],
                    "task_states": [
                        "submitted", "working", "completed", "failed", "rejected", "canceled"
                    ],
                }
            ]
        }
    )


async def create_task(request: Request) -> JSONResponse:
    tenant, scopes = _identity(request)
    if tenant != "tenant-a":
        return JSONResponse({"code": "FORBIDDEN", "message": "租户无权访问"}, status_code=403)
    denied = _require_scope(scopes, "report:create")
    if denied:
        return denied
    try:
        payload = CustomTaskRequest.model_validate(await request.json())
        submission = request.app.state.task_service.submit(
            tenant=tenant,
            idempotency_key=request.headers.get("idempotency-key", ""),
            summary=payload.summary,
            trace_id=payload.trace_id,
        )
    except ValidationError:
        return JSONResponse({"code": "INVALID_REQUEST", "message": "请求字段不合法"}, status_code=422)
    except LifecycleError as exc:
        status = 409 if exc.code == "IDEMPOTENCY_CONFLICT" else 422
        return JSONResponse({"code": exc.code, "message": exc.message}, status_code=status)
    return JSONResponse(
        submission.task.model_dump(mode="json"),
        status_code=200 if submission.replayed else 202,
        headers={"Idempotent-Replay": str(submission.replayed).lower()},
    )


async def run_task(request: Request) -> JSONResponse:
    tenant, scopes = _identity(request)
    denied = _require_scope(scopes, "report:execute")
    if denied:
        return denied
    service: TaskLifecycleService = request.app.state.task_service
    try:
        task = service.start(request.path_params["task_id"], tenant)
        artifact = request.app.state.report_renderer(task.summary)
        completed = service.complete(task.id, tenant, artifact)
        return JSONResponse(completed.model_dump(mode="json"))
    except LifecycleError as exc:
        status = 404 if exc.code == "TASK_NOT_FOUND" else 409
        return JSONResponse({"code": exc.code, "message": exc.message}, status_code=status)
    except Exception as exc:
        # 私有协议还必须自己决定如何映射执行异常；只暴露稳定错误类型。
        task_id = request.path_params["task_id"]
        try:
            failed = service.fail(task_id, tenant, "REPORT_GENERATION_FAILED")
        except LifecycleError:
            return JSONResponse({"code": "TASK_RUN_FAILED", "message": "任务执行失败"}, status_code=500)
        return JSONResponse(
            {
                **failed.model_dump(mode="json"),
                "error": {"code": "REPORT_GENERATION_FAILED", "type": type(exc).__name__},
            },
            status_code=500,
        )


async def get_task(request: Request) -> JSONResponse:
    tenant, _ = _identity(request)
    try:
        task = request.app.state.task_service.get(request.path_params["task_id"], tenant)
    except LifecycleError as exc:
        return JSONResponse({"code": exc.code, "message": exc.message}, status_code=404)
    return JSONResponse(task.model_dump(mode="json"))


async def get_task_events(request: Request) -> JSONResponse:
    tenant, _ = _identity(request)
    try:
        after = int(request.query_params.get("after", "0"))
        events = request.app.state.task_service.events(
            request.path_params["task_id"], tenant, after=after
        )
    except ValueError:
        return JSONResponse({"code": "INVALID_CURSOR", "message": "事件游标不合法"}, status_code=422)
    except LifecycleError as exc:
        status = 404 if exc.code == "TASK_NOT_FOUND" else 422
        return JSONResponse({"code": exc.code, "message": exc.message}, status_code=status)
    return JSONResponse({"events": [event.model_dump(mode="json") for event in events]})


async def cancel_task(request: Request) -> JSONResponse:
    tenant, scopes = _identity(request)
    denied = _require_scope(scopes, "report:cancel")
    if denied:
        return denied
    try:
        updated = request.app.state.task_service.cancel(request.path_params["task_id"], tenant)
    except LifecycleError as exc:
        status = 404 if exc.code == "TASK_NOT_FOUND" else 409
        return JSONResponse({"code": exc.code, "message": exc.message}, status_code=status)
    return JSONResponse(updated.model_dump(mode="json"))


def _render_report(summary: dict[str, int | float]) -> str:
    return f"# 管理报告\n\n{json.dumps(summary, ensure_ascii=False, sort_keys=True)}"


def build_custom_http_app(
    task_service: TaskLifecycleService | None = None,
    report_renderer: Callable[[dict[str, int | float]], str] | None = None,
) -> Starlette:
    app = Starlette(
        routes=[
            Route("/agents", list_agents, methods=["GET"]),
            Route("/tasks", create_task, methods=["POST"]),
            Route("/tasks/{task_id}", get_task, methods=["GET"]),
            Route("/tasks/{task_id}:run", run_task, methods=["POST"]),
            Route("/tasks/{task_id}:cancel", cancel_task, methods=["POST"]),
            Route("/tasks/{task_id}/events", get_task_events, methods=["GET"]),
        ]
    )
    app.state.task_service = task_service or TASK_SERVICE
    app.state.report_renderer = report_renderer or _render_report
    return app


custom_http_app = build_custom_http_app()
