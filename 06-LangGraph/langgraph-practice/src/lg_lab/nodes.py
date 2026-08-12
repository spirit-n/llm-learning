"""工作流节点：模型可生成候选，权限/策略/重试/验证必须保持确定性。"""

from __future__ import annotations

import uuid
from typing import Literal

from langgraph.types import interrupt

from lg_lab.sql_policy import inspect_sql
from lg_lab.state import ErrorRecord, StateVersionError, WorkflowState, migrate_state
from lg_lab.warehouse import DemoWarehouse, TransientWarehouseError, Warehouse


MAX_ATTEMPTS = 3


def _error(code: str, message: str, node: str, *, retryable: bool) -> ErrorRecord:
    return {"code": code, "message": message, "node": node, "retryable": retryable}


def validate(state: WorkflowState) -> dict:
    try:
        state, migration_trace = migrate_state(state)
    except StateVersionError as exc:
        message = str(exc)
        return {
            "status": "failed",
            "error_code": "UNSUPPORTED_STATE_VERSION",
            "error": message,
            "trace": ["validate:unsupported_state_version"],
            "error_history": [
                _error("UNSUPPORTED_STATE_VERSION", message, "validate", retryable=False)
            ],
        }
    question = state.get("question", "").strip()
    if not question:
        message = "问题不能为空"
        return {
            "status": "failed",
            "error_code": "EMPTY_QUESTION",
            "error": message,
            "trace": ["validate:rejected"],
            "error_history": [_error("EMPTY_QUESTION", message, "validate", retryable=False)],
        }
    if len(question) > 1_000:
        message = "问题超过 1000 字符"
        return {
            "status": "failed",
            "error_code": "QUESTION_TOO_LONG",
            "error": message,
            "trace": ["validate:rejected"],
            "error_history": [_error("QUESTION_TOO_LONG", message, "validate", retryable=False)],
        }
    # 生产调用方应传入网关 request_id；fallback 只为本地 demo，且不能按问题生成，
    # 否则两个独立请求会误用同一个幂等键并读到旧结果。
    request_id = state.get("request_id") or f"req-{uuid.uuid4().hex[:12]}"
    max_attempts = state.get("max_attempts", MAX_ATTEMPTS)
    failures_remaining = state.get("failures_remaining", 0)
    allowed_tables = state.get("allowed_tables", ["daily_metrics"])
    invalid_policy = (
        not isinstance(max_attempts, int)
        or isinstance(max_attempts, bool)
        or not 1 <= max_attempts <= 10
        or not isinstance(failures_remaining, int)
        or isinstance(failures_remaining, bool)
        or not 0 <= failures_remaining <= 100
    )
    if invalid_policy:
        message = "max_attempts 必须在 1..10"
        return {
            "status": "failed",
            "error_code": "INVALID_RETRY_POLICY",
            "error": message,
            "trace": ["validate:rejected"],
            "error_history": [
                _error("INVALID_RETRY_POLICY", message, "validate", retryable=False)
            ],
        }
    if not isinstance(allowed_tables, list) or any(
        not isinstance(table, str) or not table for table in allowed_tables
    ):
        message = "allowed_tables 必须是非空字符串列表"
        return {
            "status": "failed",
            "error_code": "INVALID_TABLE_POLICY",
            "error": message,
            "trace": ["validate:rejected"],
            "error_history": [
                _error("INVALID_TABLE_POLICY", message, "validate", retryable=False)
            ],
        }
    return {
        "state_version": 1,
        "request_id": request_id,
        "question": question,
        "user_id": state.get("user_id", "demo-user"),
        "role": state.get("role", "analyst"),
        "allowed_tables": allowed_tables,
        "max_attempts": max_attempts,
        "attempts": state.get("attempts", 0),
        "retries": state.get("retries", 0),
        "status": "running",
        "error_code": "",
        "error": "",
        "trace": [*migration_trace, "validate:passed"],
    }


def after_validate(state: WorkflowState) -> Literal["classify", "answer"]:
    return "answer" if state.get("error_code") else "classify"


def classify(state: WorkflowState) -> dict:
    data_words = ("多少", "昨天", "本月", "收入", "查询", "top", "删除")
    intent = (
        "data_query"
        if any(word in state["question"].lower() for word in data_words)
        else "knowledge"
    )
    return {"intent": intent, "trace": [f"classify:{intent}"]}


def after_classify(state: WorkflowState) -> Literal["schema", "answer"]:
    return "schema" if state["intent"] == "data_query" else "answer"


def retrieve_schema(state: WorkflowState) -> dict:
    # Schema 检索也要受 allowlist 约束；这里仅返回用户已获授权的教学表。
    if "daily_metrics" not in state.get("allowed_tables", []):
        message = "当前用户无可用数据表"
        return {
            "error_code": "SCHEMA_PERMISSION_DENIED",
            "error": message,
            "status": "failed",
            "trace": ["retrieve_schema:rejected"],
            "error_history": [
                _error("SCHEMA_PERMISSION_DENIED", message, "retrieve_schema", retryable=False)
            ],
        }
    return {
        "schema": (
            "daily_metrics(day TEXT, revenue REAL, success_count INTEGER, "
            "request_count INTEGER)"
        ),
        "trace": ["retrieve_schema:success"],
    }


def after_schema(state: WorkflowState) -> Literal["draft_sql", "answer"]:
    return "answer" if state.get("error_code") else "draft_sql"


def draft_sql(state: WorkflowState) -> dict:
    question = state["question"].lower()
    if "删除" in question or "delete" in question:
        sql = "DELETE FROM daily_metrics"
    elif "成功率" in question:
        # NULLIF 是确定性防护，避免 request_count=0 导致执行异常。
        sql = (
            "SELECT day, success_count * 1.0 / NULLIF(request_count, 0) "
            "AS success_rate FROM daily_metrics ORDER BY day DESC LIMIT 1"
        )
    else:
        sql = "SELECT day, revenue FROM daily_metrics ORDER BY day DESC LIMIT 1"
    return {"sql": sql, "trace": ["draft_sql:generated"]}


def sql_guard(state: WorkflowState) -> dict:
    result = inspect_sql(
        state.get("sql", ""),
        allowed_tables=set(state.get("allowed_tables", ["daily_metrics"])),
    )
    if not result.allowed:
        message = f"SQL Guard 拒绝：{result.reason}"
        return {
            "sql_fingerprint": result.fingerprint,
            "risk_level": "high",
            "status": "failed",
            "error_code": "SQL_POLICY_DENIED",
            "error": message,
            "trace": ["guard:rejected"],
            "error_history": [
                _error("SQL_POLICY_DENIED", message, "guard", retryable=False)
            ],
        }
    execution_key = f"{state.get('request_id', 'request')}:{result.fingerprint}"
    return {
        "sql_fingerprint": result.fingerprint,
        "execution_key": execution_key,
        "risk_level": result.risk_level,
        "error_code": "",
        "error": "",
        "trace": ["guard:passed"],
    }


def after_guard(state: WorkflowState) -> Literal["review", "answer"]:
    return "answer" if state.get("error_code") else "review"


def human_review(state: WorkflowState) -> dict:
    decision = interrupt(
        {
            "question": state["question"],
            "sql": state["sql"],
            "sql_fingerprint": state["sql_fingerprint"],
            "risk_level": state["risk_level"],
            "prompt": "是否批准执行？",
        }
    )
    if not isinstance(decision, bool):
        message = "人工审核结果必须是布尔值"
        return {
            "approved": False,
            "status": "failed",
            "error_code": "INVALID_REVIEW_DECISION",
            "error": message,
            "trace": ["review:invalid"],
            "error_history": [
                _error("INVALID_REVIEW_DECISION", message, "review", retryable=False)
            ],
        }
    if not decision:
        message = "用户拒绝执行 SQL"
        return {
            "approved": False,
            "status": "cancelled",
            "error_code": "USER_REJECTED",
            "error": message,
            "trace": ["review:rejected"],
            "error_history": [
                _error("USER_REJECTED", message, "review", retryable=False)
            ],
        }
    return {"approved": True, "trace": ["review:approved"]}


def after_review(state: WorkflowState) -> Literal["execute", "answer"]:
    return "execute" if state.get("approved") else "answer"


def execute(state: WorkflowState, *, warehouse: Warehouse | None = None) -> dict:
    warehouse = warehouse or DemoWarehouse()
    attempts = state.get("attempts", 0) + 1
    remaining = state.get("failures_remaining", 0)
    try:
        rows, replayed = warehouse.query(
            state["sql"],
            idempotency_key=state["execution_key"],
            simulate_transient=remaining > 0,
        )
    except TransientWarehouseError as exc:
        message = str(exc)
        return {
            "attempts": attempts,
            "retries": state.get("retries", 0) + 1,
            "failures_remaining": max(remaining - 1, 0),
            "status": "running",
            "error_code": "WAREHOUSE_TRANSIENT",
            "error": message,
            "trace": [f"execute:transient:{attempts}"],
            "error_history": [
                _error("WAREHOUSE_TRANSIENT", message, "execute", retryable=True)
            ],
        }
    return {
        "attempts": attempts,
        "rows": rows,
        "execution_completed": True,
        "status": "running",
        "error_code": "",
        "error": "",
        "trace": ["execute:idempotent_replay" if replayed else "execute:success"],
    }


def after_execute(state: WorkflowState) -> Literal["retry", "verify", "answer"]:
    if state.get("error_code") == "WAREHOUSE_TRANSIENT":
        if state.get("attempts", 0) < state.get("max_attempts", MAX_ATTEMPTS):
            return "retry"
        return "answer"
    return "verify"


def verify_result(state: WorkflowState) -> dict:
    rows = state.get("rows", [])
    if not rows:
        message = "查询成功但没有数据"
        return {
            "verification_passed": False,
            "status": "failed",
            "error_code": "NO_DATA",
            "error": message,
            "trace": ["verify:no_data"],
            "error_history": [_error("NO_DATA", message, "verify", retryable=False)],
        }
    first = rows[0]
    if "success_rate" in first:
        value = first["success_rate"]
        if not isinstance(value, (int, float)) or not 0 <= value <= 1:
            message = "成功率结果不在 0..1"
            return {
                "verification_passed": False,
                "status": "failed",
                "error_code": "RESULT_VALIDATION_FAILED",
                "error": message,
                "trace": ["verify:rejected"],
                "error_history": [
                    _error("RESULT_VALIDATION_FAILED", message, "verify", retryable=False)
                ],
            }
    return {"verification_passed": True, "trace": ["verify:passed"]}


def after_verify(state: WorkflowState) -> Literal["answer"]:
    return "answer"


def answer(state: WorkflowState) -> dict:
    error_code = state.get("error_code", "")
    if error_code:
        status = "cancelled" if error_code == "USER_REJECTED" else "failed"
        prefix = "处理未完成" if status == "cancelled" else "处理失败"
        text = f"{prefix}：{state.get('error', error_code)}"
        if error_code == "WAREHOUSE_TRANSIENT":
            text += f"（共尝试 {state.get('attempts', 0)} 次）"
    elif state.get("intent") == "knowledge":
        status = "completed"
        text = "成功率表示成功请求数占总请求数的比例。"
    elif state.get("verification_passed"):
        status = "completed"
        text = f"查询结果：{state['rows'][0]}"
    else:
        status = "failed"
        text = "处理未完成：结果未通过验证。"
        error_code = "UNVERIFIED_RESULT"
    return {
        "status": status,
        "answer": text,
        "error_code": error_code,
        "trace": [f"answer:{status}"],
    }
