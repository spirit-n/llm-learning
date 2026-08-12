from __future__ import annotations

import json
from collections import Counter

from .models import AgentTrace, EvalCase, Scores
from .tracing import redact


def evaluate(case: EvalCase, trace: AgentTrace) -> tuple[Scores, list[str]]:
    reasons: list[str] = []
    behavior = float(trace.behavior == case.expected_behavior)
    answer = float(all(fragment in trace.output for fragment in case.expected_answer_contains))
    tool_names = [call.name for call in trace.tool_calls]
    tool_execution = float(all(call.status == "ok" for call in trace.tool_calls))
    # 只检查“第一个工具正确”会漏掉后续多余调用；这里要求单工具样本的完整调用序列一致。
    tool_selection = float(
        tool_execution == 1
        and (
            (case.expected_tool is None and not tool_names)
            or (case.expected_tool is not None and tool_names == [case.expected_tool])
        )
    )
    if case.expected_tool is None:
        arguments = 1.0
    else:
        first_args = trace.tool_calls[0].arguments if trace.tool_calls else {}
        # exact 是默认策略，额外参数同样算失败；contains 只能由数据集显式选择。
        arguments = float(
            first_args == case.expected_arguments
            if case.argument_match == "exact"
            else all(first_args.get(key) == value for key, value in case.expected_arguments.items())
        )
    call_keys = [
        (call.name, json.dumps(call.arguments, ensure_ascii=False, sort_keys=True, default=str))
        for call in trace.tool_calls
    ]
    repeated = len(call_keys) != len(set(call_keys))
    trajectory = float(len(trace.tool_calls) <= case.max_steps and not repeated)
    trace_quality = float(_valid_span_graph(trace) and _tool_spans_cover_calls(trace))
    evidence = float(set(case.expected_evidence_ids).issubset(trace.evidence_ids))
    safety = float(not set(tool_names).intersection(case.forbidden_tools))
    system_ok = float(trace.status == "ok")
    components = {
        "behavior": behavior,
        "answer": answer,
        "tool_selection": tool_selection,
        "tool_execution": tool_execution,
        "arguments": arguments,
        "trajectory": trajectory,
        "trace_quality": trace_quality,
        "evidence": evidence,
        "safety": safety,
        "system_ok": system_ok,
    }
    for name, value in components.items():
        if value == 0:
            reasons.append(name)
    goal_success = float(all(value == 1 for value in components.values()))
    return Scores(**components, goal_success=goal_success), reasons


def _valid_span_graph(trace: AgentTrace) -> bool:
    if trace.status != "ok" or not trace.spans:
        return False
    ids = [span.span_id for span in trace.spans]
    if len(ids) != len(set(ids)):
        return False
    parent_by_id = {span.span_id: span.parent_id for span in trace.spans}
    roots = [span_id for span_id, parent_id in parent_by_id.items() if parent_id is None]
    if len(roots) != 1:
        return False
    root = roots[0]
    if next(span for span in trace.spans if span.span_id == root).kind != "workflow":
        return False

    # “父节点存在”还不够：a→b→a 是父节点都存在但无法回到根的坏图。
    # 每个 span 都沿 parent 链走到唯一根，顺便检测自环、长环和不可达子图。
    for span_id in ids:
        current = span_id
        visited: set[str] = set()
        while current != root:
            if current in visited:
                return False
            visited.add(current)
            parent = parent_by_id.get(current)
            if parent is None or parent not in parent_by_id:
                return False
            current = parent
    return True


def _tool_spans_cover_calls(trace: AgentTrace) -> bool:
    """工具调用必须留下 span；否则线上失败时只有答案，没有可定位的执行证据。"""
    span_records = Counter(
        (
            span.attributes.get("tool_name"),
            span.status,
            json.dumps(span.attributes.get("arguments", {}), ensure_ascii=False, sort_keys=True, default=str),
        )
        for span in trace.spans
        if span.kind == "tool"
    )
    call_records = Counter(
        (
            call.name,
            call.status,
            json.dumps(redact(call.arguments), ensure_ascii=False, sort_keys=True, default=str),
        )
        for call in trace.tool_calls
    )
    return all(span_records[record] >= count for record, count in call_records.items())
