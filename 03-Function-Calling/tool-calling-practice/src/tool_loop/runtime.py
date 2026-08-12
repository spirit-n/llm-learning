from __future__ import annotations

import hashlib
import json
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from typing import Protocol

from pydantic import ValidationError

from .guards import GuardDenied, limit_output
from .models import (
    AuditEvent,
    Message,
    ModelResponse,
    RunResult,
    ToolCall,
    ToolResult,
    UserContext,
)
from .registry import ToolRegistry, ToolSpec


class ChatModel(Protocol):
    def complete(
        self,
        messages: list[Message],
        tool_schemas: list[dict],
    ) -> ModelResponse: ...


class ToolRuntime:
    def __init__(self, registry: ToolRegistry, *, max_steps: int = 6) -> None:
        if max_steps < 1:
            raise ValueError("max_steps 必须大于 0")
        self.registry = registry
        self.max_steps = max_steps

    def run(
        self,
        model: ChatModel,
        user_prompt: str,
        user: UserContext,
    ) -> RunResult:
        messages = [Message(role="user", content=user_prompt)]
        audit_log: list[AuditEvent] = []
        seen_calls: set[str] = set()
        tool_call_count = 0
        invalid_call_count = 0

        for step in range(1, self.max_steps + 1):
            response = model.complete(list(messages), self.registry.model_schemas())

            if response.final_answer is not None:
                messages.append(Message(role="assistant", content=response.final_answer))
                return RunResult(
                    status="completed",
                    final_answer=response.final_answer,
                    messages=messages,
                    audit_log=audit_log,
                    steps=step,
                    tool_call_count=tool_call_count,
                    invalid_call_count=invalid_call_count,
                )

            messages.append(
                Message(
                    role="assistant",
                    content=json.dumps(
                        {"tool_calls": [call.model_dump() for call in response.tool_calls]},
                        ensure_ascii=False,
                    ),
                )
            )

            for call in response.tool_calls:
                signature = self._call_signature(call)
                if signature in seen_calls:
                    result = ToolResult(
                        status="error",
                        error_code="REPEATED_TOOL_CALL",
                        message="检测到重复工具调用，循环已停止",
                    )
                    messages.append(self._tool_message(call, result))
                    audit_log.append(
                        AuditEvent(
                            step=step,
                            call_id=call.id,
                            tool_name=call.name,
                            arguments_digest=self._digest(signature),
                            outcome="error",
                            error_code="REPEATED_TOOL_CALL",
                            duration_ms=0,
                        )
                    )
                    return RunResult(
                        status="stopped",
                        error_code="REPEATED_TOOL_CALL",
                        messages=messages,
                        audit_log=audit_log,
                        steps=step,
                        tool_call_count=tool_call_count + 1,
                        invalid_call_count=invalid_call_count + 1,
                    )

                seen_calls.add(signature)
                tool_call_count += 1
                result, event = self._execute_call(call, user, step, signature)
                audit_log.append(event)
                messages.append(self._tool_message(call, result))
                if result.status != "ok":
                    invalid_call_count += 1

        return RunResult(
            status="max_steps",
            error_code="MAX_STEPS_EXCEEDED",
            messages=messages,
            audit_log=audit_log,
            steps=self.max_steps,
            tool_call_count=tool_call_count,
            invalid_call_count=invalid_call_count,
        )

    def _execute_call(
        self,
        call: ToolCall,
        user: UserContext,
        step: int,
        signature: str,
    ) -> tuple[ToolResult, AuditEvent]:
        started = time.perf_counter()
        spec = self.registry.get(call.name)

        if spec is None:
            result = ToolResult(
                status="error",
                error_code="UNKNOWN_TOOL",
                message=f"未知工具：{call.name}",
            )
            return result, self._audit(step, call, signature, result, started)

        try:
            args = spec.args_model.model_validate(call.arguments)
        except ValidationError as exc:
            fields = sorted(
                {
                    ".".join(str(part) for part in error["loc"])
                    for error in exc.errors()
                }
            )
            result = ToolResult(
                status="error",
                error_code="INVALID_ARGUMENTS",
                message=f"参数校验失败：{', '.join(fields)}",
            )
            return result, self._audit(step, call, signature, result, started)

        if spec.required_permission and spec.required_permission not in user.permissions:
            result = ToolResult(
                status="denied",
                error_code="PERMISSION_DENIED",
                message=f"缺少权限：{spec.required_permission}",
            )
            return result, self._audit(step, call, signature, result, started)

        result = self._run_with_timeout(spec, args)
        return result, self._audit(step, call, signature, result, started)

    def _run_with_timeout(self, spec: ToolSpec, args: object) -> ToolResult:
        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix=f"tool-{spec.name}")
        future = executor.submit(spec.handler, args)
        try:
            raw_data = future.result(timeout=spec.timeout_seconds)
            data, truncated, original_bytes = limit_output(
                raw_data,
                spec.output_limit_bytes,
            )
            return ToolResult(
                status="ok",
                data=data,
                truncated=truncated,
                original_bytes=original_bytes,
            )
        except FutureTimeoutError:
            future.cancel()
            return ToolResult(
                status="error",
                error_code="TOOL_TIMEOUT",
                message="工具执行超时",
            )
        except GuardDenied as exc:
            return ToolResult(
                status="denied",
                error_code=exc.code,
                message=exc.public_message,
            )
        except Exception:
            return ToolResult(
                status="error",
                error_code="TOOL_EXECUTION_ERROR",
                message="工具执行失败",
            )
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    @staticmethod
    def _call_signature(call: ToolCall) -> str:
        canonical_arguments = json.dumps(
            call.arguments,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        return f"{call.name}:{canonical_arguments}"

    @staticmethod
    def _digest(signature: str) -> str:
        return hashlib.sha256(signature.encode("utf-8")).hexdigest()[:12]

    @staticmethod
    def _tool_message(call: ToolCall, result: ToolResult) -> Message:
        return Message(
            role="tool",
            name=call.name,
            tool_call_id=call.id,
            content=result.model_dump_json(),
        )

    def _audit(
        self,
        step: int,
        call: ToolCall,
        signature: str,
        result: ToolResult,
        started: float,
    ) -> AuditEvent:
        return AuditEvent(
            step=step,
            call_id=call.id,
            tool_name=call.name,
            arguments_digest=self._digest(signature),
            outcome=result.status,
            error_code=result.error_code,
            duration_ms=round((time.perf_counter() - started) * 1000, 3),
            truncated=result.truncated,
        )

