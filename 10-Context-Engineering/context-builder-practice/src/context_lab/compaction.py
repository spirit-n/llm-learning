"""确定性多轮压缩/恢复：丢弃讨论文本，保留可校验工作状态及外部证据引用。

这是结构化事件归约器，不是 LLM 自由文本摘要器；事件必须由可信运行时构造。
"""

from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt

from context_lab.builder import estimate_tokens


class TurnEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    sequence: int = Field(ge=1)
    kind: Literal["task", "decision", "todo", "done", "evidence", "note"]
    key: str = Field(min_length=1)
    value: str = Field(min_length=1)


class Checkpoint(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1] = 1
    tenant: str = Field(min_length=1)
    task: str = Field(min_length=1)
    last_sequence: int = Field(ge=1)
    decisions: dict[str, str]
    pending: dict[str, str]
    completed: tuple[str, ...] = ()
    evidence_refs: dict[str, str]


class CountsEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    tenant: str
    success_count: StrictInt = Field(ge=0)
    total_count: StrictInt = Field(gt=0)


class RecoveryError(ValueError):
    pass


def compact_trace(
    events: list[TurnEvent], *, tenant: str, previous: Checkpoint | None = None
) -> Checkpoint:
    """在已有 checkpoint 上压缩下一批事件，拒绝乱序、重复和隐式换任务。"""
    if previous and previous.tenant != tenant:
        raise RecoveryError("CHECKPOINT_TENANT_MISMATCH")
    task = previous.task if previous else ""
    sequence = previous.last_sequence if previous else 0
    decisions = dict(previous.decisions) if previous else {}
    pending = dict(previous.pending) if previous else {}
    completed = list(previous.completed) if previous else []
    references = dict(previous.evidence_refs) if previous else {}
    for event in events:
        if event.sequence <= sequence:
            raise RecoveryError("EVENT_SEQUENCE_NOT_INCREASING")
        sequence = event.sequence
        if event.kind == "task":
            if task and task != event.value:
                raise RecoveryError("TASK_CHANGED_REQUIRES_NEW_CHECKPOINT")
            task = event.value
        elif event.kind == "decision":
            decisions[event.key] = event.value
        elif event.kind == "todo":
            if event.key in completed:
                raise RecoveryError("COMPLETED_ACTION_CANNOT_REOPEN")
            pending[event.key] = event.value
        elif event.kind == "done":
            if event.key not in pending:
                raise RecoveryError("DONE_WITHOUT_PENDING_ACTION")
            del pending[event.key]
            completed.append(event.key)
        elif event.kind == "evidence":
            references[event.key] = event.value
        # note 是可丢弃的讨论，不从其文本中提取指令、决定或事实。
    if not task.strip():
        raise RecoveryError("TASK_MISSING")
    return Checkpoint(
        tenant=tenant, task=task, last_sequence=sequence, decisions=decisions,
        pending=pending, completed=tuple(completed), evidence_refs=references,
    )


def resume_next_action(
    checkpoint: Checkpoint, evidence_store: dict[str, CountsEvidence]
) -> dict[str, object]:
    """恢复教学报告流程的一步；无证据、错误口径或缺失待办时不猜答案。"""
    if checkpoint.decisions.get("denominator") != "all_requests":
        raise RecoveryError("DENOMINATOR_DECISION_MISSING_OR_UNSUPPORTED")
    ref = checkpoint.evidence_refs.get("counts")
    evidence = evidence_store.get(ref or "")
    if evidence is None or evidence.tenant != checkpoint.tenant:
        raise RecoveryError("EVIDENCE_NOT_AVAILABLE")
    if evidence.success_count > evidence.total_count:
        raise RecoveryError("COUNTS_INCONSISTENT")
    percentage = f"{evidence.success_count / evidence.total_count * 100:.2f}%"
    if "verify_rate" in checkpoint.pending:
        action = "verify_rate"
        output = f"已核验成功率 {percentage}"
    elif "draft_report" in checkpoint.pending and "verify_rate" in checkpoint.completed:
        action = "draft_report"
        output = f"{checkpoint.task}：成功率 {percentage}；证据 {ref}。"
    else:
        raise RecoveryError("RECOVERABLE_ACTION_MISSING")
    return {"action": action, "percentage": percentage, "source_ref": ref, "output": output}


def sample_trace() -> list[TurnEvent]:
    rows = [
        ("task", "goal", "报告 tenant-a 的成功率"),
        ("decision", "denominator", "all_requests"),
        ("todo", "verify_rate", "回查聚合证据并核算成功率"),
        ("todo", "draft_report", "产出带来源引用的报告"),
        ("evidence", "counts", "query-42"),
    ]
    rows.extend(("note", f"discussion-{i}", "可丢弃的讨论与重复工具日志。" * 20) for i in range(30))
    return [TurnEvent(sequence=i, kind=kind, key=key, value=value)
            for i, (kind, key, value) in enumerate(rows, 1)]


def run_compaction_experiment() -> dict[str, object]:
    trace = sample_trace()
    store = {"query-42": CountsEvidence(tenant="tenant-a", success_count=90, total_count=100)}
    first = compact_trace(trace, tenant="tenant-a")
    # JSON 往返模拟新上下文/新进程；恢复函数只拿 checkpoint，不再接收原始历史。
    restored = Checkpoint.model_validate_json(first.model_dump_json())
    facts = {
        "task": restored.task == "报告 tenant-a 的成功率",
        "decision": restored.decisions.get("denominator") == "all_requests",
        "pending_verification": "verify_rate" in restored.pending,
        "pending_report": "draft_report" in restored.pending,
        "evidence_reference": restored.evidence_refs.get("counts") == "query-42",
    }
    verified = resume_next_action(restored, store)
    second = compact_trace([
        TurnEvent(sequence=36, kind="done", key="verify_rate", value="已核验"),
        TurnEvent(sequence=37, kind="note", key="noise", value="更多可丢弃讨论" * 40),
    ], tenant="tenant-a", previous=restored)
    restored_again = Checkpoint.model_validate_json(second.model_dump_json())
    report = resume_next_action(restored_again, store)
    finished = compact_trace([
        TurnEvent(sequence=38, kind="done", key="draft_report", value="报告已生成"),
    ], tenant="tenant-a", previous=restored_again)
    negative_controls: dict[str, bool] = {}
    for name, changes in (
        ("missing_decision", {"decisions": {}}),
        ("missing_pending", {"pending": {}}),
        ("missing_evidence", {"evidence_refs": {}}),
    ):
        damaged = Checkpoint.model_validate({**first.model_dump(), **changes})
        try:
            resume_next_action(damaged, store)
        except RecoveryError:
            negative_controls[name] = True
        else:
            negative_controls[name] = False
    try:
        compact_trace(trace[-4:], tenant="tenant-a")
    except RecoveryError:
        negative_controls["sliding_window_lost_task"] = True
    raw = json.dumps([event.model_dump() for event in trace], ensure_ascii=False)
    return {
        "semantic_facts": facts,
        "semantic_fact_recall": sum(facts.values()) / len(facts),
        "compression_boundaries": 2,
        "resumed_actions": [verified["action"], report["action"]],
        "recovery_success": verified["percentage"] == "90.00%" and not finished.pending,
        "report": report["output"],
        "negative_controls_rejected": negative_controls,
        "original_estimated_tokens": estimate_tokens(raw),
        "checkpoint_estimated_tokens": estimate_tokens(first.model_dump_json()),
    }


if __name__ == "__main__":
    print(json.dumps(run_compaction_experiment(), ensure_ascii=False, indent=2))
