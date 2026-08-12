import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from eval_lab.app import DemoMetricAgent
from eval_lab.dataset import dataset_fingerprint, load_dataset
from eval_lab.evaluators import evaluate
from eval_lab.judge import parse_judge_decision
from eval_lab.models import AgentTrace, EvalInput, Span
from eval_lab.reporting import write_report
from eval_lab.runner import EvalRunner, evaluate_regression_gate, percentile, regression_gate, wilson_interval
from eval_lab.tracing import TraceCollector


DATASET = Path(__file__).resolve().parents[1] / "evals" / "datasets" / "metric_agent_v1.jsonl"


def cases():
    return load_dataset(DATASET)


def run_direct(agent: DemoMetricAgent, case):
    """绕过 Runner 做组件测试时，也只把公开输入交给被测系统。"""
    return agent.run(EvalInput(case_id=case.id, user_input=case.input))


def test_golden_set_has_20_unique_valid_cases():
    values = cases()
    assert len(values) == 20
    assert len({case.id for case in values}) == 20
    assert {"normal", "boundary", "safety", "recovery"}.issubset({tag for case in values for tag in case.tags})


def test_candidate_passes_every_golden_case():
    report = EvalRunner().run(DemoMetricAgent("candidate"), cases())
    assert report.dataset_size == 20
    assert report.metrics["goal_success"] == 1.0
    assert report.failures == []


def test_baseline_keeps_system_error_as_a_failed_case():
    report = EvalRunner().run(DemoMetricAgent("baseline"), cases())
    result = next(item for item in report.results if item.case.id == "q20")
    assert result.trace.status == "error"
    assert result.trace.error_code == "RuntimeError"
    assert result.scores.goal_success == 0


def test_component_graders_explain_different_failure_types():
    report = EvalRunner().run(DemoMetricAgent("baseline"), cases())
    failures = {result.case.id: result.failure_reasons for result in report.results if result.failure_reasons}
    assert "tool_selection" in failures["q05"]
    assert "answer" in failures["q09"]
    assert "arguments" in failures["q11"]
    assert "safety" in failures["q14"]
    assert "trajectory" in failures["q17"]


def test_candidate_improves_baseline_without_regression():
    runner = EvalRunner()
    baseline = runner.run(DemoMetricAgent("baseline"), cases())
    candidate = runner.run(DemoMetricAgent("candidate"), cases())
    assert candidate.metrics["goal_success"] > baseline.metrics["goal_success"]
    assert regression_gate(baseline, candidate) == []


def test_broken_candidate_is_stopped_by_regression_gate():
    runner = EvalRunner()
    baseline = runner.run(DemoMetricAgent("candidate"), cases())
    broken = runner.run(DemoMetricAgent("broken"), cases())
    failures = regression_gate(baseline, broken)
    assert "goal_success_regressed" in failures
    assert "safety_regressed" in failures


def test_report_has_tag_slices_and_latency_percentiles():
    report = EvalRunner().run(DemoMetricAgent("candidate"), cases())
    assert report.by_tag["safety"]["samples"] == 4
    assert report.by_tag["safety"]["goal_success"] == 1
    assert 0 <= report.by_tag["safety"]["goal_success_ci_low"] < 1
    assert report.metrics["latency_p95_ms"] >= report.metrics["latency_p50_ms"]
    assert report.metrics["weighted_goal_success"] == 1


def test_trace_has_parent_child_spans_and_redacts_secret_fields():
    trace = run_direct(DemoMetricAgent("candidate"), cases()[0])
    root = next(span for span in trace.spans if span.name == "agent.run")
    assert root.attributes["api_key"] == "[REDACTED]"
    assert any(span.parent_id == root.span_id for span in trace.spans)


def test_trace_collector_marks_failed_span():
    collector = TraceCollector()
    try:
        with collector.span("explode", password="secret", note="Bearer abcdefghijklmnop"):
            raise ValueError("boom")
    except ValueError:
        pass
    assert collector.spans[0].status == "error"
    assert collector.spans[0].attributes["password"] == "[REDACTED]"
    assert "abcdefghijklmnop" not in collector.spans[0].attributes["note"]


def test_report_writer_preserves_raw_json_and_human_summary(tmp_path):
    report = EvalRunner().run(DemoMetricAgent("candidate"), cases())
    json_path, markdown_path = write_report(report, tmp_path)
    assert json.loads(json_path.read_text(encoding="utf-8"))["dataset_size"] == 20
    assert "goal_success" in markdown_path.read_text(encoding="utf-8")
    assert (tmp_path / f"candidate-{report.run_id[:12]}.traces.jsonl").exists()


def test_percentile_handles_empty_and_nonempty_values():
    assert percentile([], 0.95) == 0
    assert percentile([1, 2, 3, 4], 0.5) == 2.5


def test_dataset_fingerprint_is_stable_and_content_sensitive():
    values = cases()
    assert dataset_fingerprint(values) == dataset_fingerprint(list(reversed(values)))
    changed = [case.model_copy(deep=True) for case in values]
    changed[0].input = "changed"
    assert dataset_fingerprint(values) != dataset_fingerprint(changed)


def test_dataset_error_reports_the_bad_line_number(tmp_path):
    path = tmp_path / "bad.jsonl"
    path.write_text(
        '{"id":"ok","input":"x","expected_behavior":"answer","tags":["normal"]}\n'
        '{"id":"bad","input":"x","expected_behavior":"refuse","expected_tool":"query","tags":["normal"]}\n',
        encoding="utf-8",
    )
    try:
        load_dataset(path)
    except ValueError as exc:
        assert "第 2 行" in str(exc)
    else:
        raise AssertionError("invalid dataset should fail")


def test_evidence_and_trace_graph_are_independent_graders():
    case = cases()[0]
    trace = run_direct(DemoMetricAgent("candidate"), case)
    missing_evidence = trace.model_copy(update={"evidence_ids": []})
    scores, reasons = evaluate(case, missing_evidence)
    assert scores.evidence == 0
    assert "evidence" in reasons

    broken_spans = [span.model_copy(deep=True) for span in trace.spans]
    broken_spans[-1].parent_id = "not-found"
    broken_trace = trace.model_copy(update={"spans": broken_spans})
    scores, reasons = evaluate(case, broken_trace)
    assert scores.trace_quality == 0
    assert "trace_quality" in reasons


def test_gate_explains_case_improvements_and_dataset_mismatch():
    runner = EvalRunner()
    baseline = runner.run(DemoMetricAgent("baseline"), cases())
    candidate = runner.run(DemoMetricAgent("candidate"), cases())
    gate = evaluate_regression_gate(baseline, candidate)
    assert gate.passed is True
    assert {"q05", "q09", "q11", "q14", "q17", "q18", "q20"}.issubset(gate.case_improvements)

    mismatched = candidate.model_copy(update={"dataset_fingerprint": "different"})
    gate = evaluate_regression_gate(baseline, mismatched)
    assert gate.passed is False
    assert "dataset_fingerprint_mismatch" in gate.failures


def test_wilson_interval_exposes_small_slice_uncertainty():
    low, high = wilson_interval(4, 4)
    assert 0 < low < high == 1


def test_system_receives_only_frozen_public_input_not_eval_oracle():
    class InspectingAgent:
        variant = "candidate"
        system_version = "metric-agent/candidate-2.1"

        def __init__(self):
            self.received = None

        def run(self, request):
            self.received = request
            return DemoMetricAgent("candidate").run(request)

    agent = InspectingAgent()
    report = EvalRunner().run(agent, [cases()[0]])
    assert report.metrics["goal_success"] == 1
    assert isinstance(agent.received, EvalInput)
    assert set(type(agent.received).model_fields) == {"case_id", "user_input"}
    assert not hasattr(agent.received, "expected_answer_contains")
    with pytest.raises(ValidationError):
        agent.received.user_input = "篡改输入"


def test_runner_validates_trace_structure_and_identity_without_stopping_batch():
    class BadTraceAgent:
        variant = "candidate"
        system_version = "metric-agent/candidate-2.1"

        def run(self, request):
            trace = DemoMetricAgent("candidate").run(request)
            if request.case_id == "q01":
                return trace.model_copy(update={"case_id": "another-case"})
            if request.case_id == "q02":
                return trace.model_copy(update={"variant": "another-variant"})
            if request.case_id == "q03":
                return trace.model_copy(update={"system_version": "another-version"})
            if request.case_id == "q04":
                return {"unexpected": "shape"}
            return trace

    report = EvalRunner().run(BadTraceAgent(), cases()[:5])
    assert report.dataset_size == 5
    assert [item.trace.status for item in report.results] == ["error", "error", "error", "error", "ok"]
    assert [item.trace.error_code for item in report.results[:3]] == ["TraceContractError"] * 3
    assert report.results[3].trace.error_code == "ValidationError"
    assert report.results[4].case.id == "q05"


def test_runner_rejects_duplicate_case_ids_and_duplicate_trace_ids():
    values = cases()
    with pytest.raises(ValueError, match="case id 重复"):
        EvalRunner().run(DemoMetricAgent("candidate"), [values[0], values[0]])

    class ReusedTraceAgent:
        variant = "candidate"
        system_version = "metric-agent/candidate-2.1"

        def run(self, request):
            trace = DemoMetricAgent("candidate").run(request)
            return trace.model_copy(update={"trace_id": "reused-trace"})

    report = EvalRunner().run(ReusedTraceAgent(), values[:2])
    assert report.results[0].trace.status == "ok"
    assert report.results[1].trace.status == "error"
    assert report.results[1].trace.error_code == "TraceContractError"


def test_runner_snapshots_system_identity_and_rejects_invalid_metadata():
    class MutatingIdentityAgent:
        variant = "candidate"
        system_version = "metric-agent/candidate-2.1"

        def run(self, request):
            trace = DemoMetricAgent("candidate").run(request)
            self.variant = "changed-during-run"
            self.system_version = "changed-during-run"
            return trace

    report = EvalRunner().run(MutatingIdentityAgent(), [cases()[0]])
    assert report.variant == "candidate"
    assert report.system_version == "metric-agent/candidate-2.1"
    assert report.metrics["goal_success"] == 1

    invalid = DemoMetricAgent("candidate")
    invalid.variant = ""
    with pytest.raises(ValueError, match="variant"):
        EvalRunner().run(invalid, [cases()[0]])


def test_runner_overrides_untrusted_self_reported_latency(monkeypatch):
    class FakeAgent:
        variant = "candidate"
        system_version = "fake/1"

        def run(self, request):
            return AgentTrace(
                trace_id="trace-1",
                case_id=request.case_id,
                variant=self.variant,
                status="ok",
                behavior="answer",
                output="x",
                spans=[Span(span_id="root", name="run", kind="workflow", status="ok", duration_ms=0)],
                latency_ms=999_999,
                prompt_tokens=0,
                completion_tokens=0,
                system_version=self.system_version,
            )

    clock = iter([10.0, 10.125])
    monkeypatch.setattr("eval_lab.runner.time.perf_counter", lambda: next(clock))
    result = EvalRunner().run(FakeAgent(), [cases()[0]]).results[0]
    assert result.trace.latency_ms == 125.0


def test_tool_execution_status_and_explicit_argument_policy_are_independent():
    case = cases()[0]
    trace = run_direct(DemoMetricAgent("candidate"), case)

    failed_call = trace.tool_calls[0].model_copy(update={"status": "error"})
    failed_trace = trace.model_copy(update={"tool_calls": [failed_call]})
    scores, reasons = evaluate(case, failed_trace)
    assert scores.tool_execution == 0
    assert scores.tool_selection == 0
    assert "tool_execution" in reasons

    extra_arguments = {**trace.tool_calls[0].arguments, "debug": True}
    extra_call = trace.tool_calls[0].model_copy(update={"arguments": extra_arguments})
    extra_spans = [span.model_copy(deep=True) for span in trace.spans]
    tool_span = next(span for span in extra_spans if span.kind == "tool")
    tool_span.attributes["arguments"] = extra_arguments
    extra_trace = trace.model_copy(update={"tool_calls": [extra_call], "spans": extra_spans})
    scores, _ = evaluate(case, extra_trace)
    assert case.argument_match == "exact"
    assert scores.arguments == 0
    contains_case = case.model_copy(update={"argument_match": "contains"})
    scores, _ = evaluate(contains_case, extra_trace)
    assert scores.arguments == 1


@pytest.mark.parametrize("corruption", ["multiple-roots", "cycle"])
def test_trace_graph_rejects_multiple_roots_cycles_and_unreachable_spans(corruption):
    case = cases()[0]
    trace = run_direct(DemoMetricAgent("candidate"), case)
    spans = [span.model_copy(deep=True) for span in trace.spans]
    children = [span for span in spans if span.parent_id is not None]
    if corruption == "multiple-roots":
        children[0].parent_id = None
    else:
        children[0].parent_id = children[1].span_id
        children[1].parent_id = children[0].span_id
    scores, reasons = evaluate(case, trace.model_copy(update={"spans": spans}))
    assert scores.trace_quality == 0
    assert "trace_quality" in reasons


def test_all_report_artifacts_recursively_redact_output_and_tool_arguments(tmp_path):
    report = EvalRunner().run(DemoMetricAgent("candidate"), [cases()[0]])
    raw_secret = "sk-report-secret-123456789"
    report.results[0].trace.output = f"api_key={raw_secret}"
    report.results[0].trace.tool_calls[0].arguments["nested"] = {
        "authorization": f"Bearer {raw_secret}"
    }
    json_path, markdown_path = write_report(report, tmp_path)
    traces_path = tmp_path / f"candidate-{report.run_id[:12]}.traces.jsonl"
    for path in (json_path, traces_path, markdown_path):
        exported = path.read_text(encoding="utf-8")
        assert raw_secret not in exported
    for path in (json_path, traces_path):
        exported = path.read_text(encoding="utf-8")
        assert "[REDACTED]" in exported
    exported_report = json.loads(json_path.read_text(encoding="utf-8"))
    exported_trace = exported_report["results"][0]["trace"]
    # token 计数是成本观测指标，不是访问令牌，不能被过宽的脱敏规则误删。
    assert exported_trace["prompt_tokens"] == report.results[0].trace.prompt_tokens
    assert exported_trace["completion_tokens"] == report.results[0].trace.completion_tokens
    # 导出清洗不应反向篡改内存中的原始观测，避免影响刚完成的评分。
    assert raw_secret in report.results[0].trace.output


def test_judge_decision_uses_strict_pydantic_contract():
    valid = parse_judge_decision(
        {"score": 0.8, "passed": True, "reasons": ["事实正确"], "critical_fact_errors": []}
    )
    assert valid.passed is True
    with pytest.raises(ValidationError):
        parse_judge_decision(
            {
                "score": "0.8",
                "passed": True,
                "reasons": ["错误类型不应被宽松转换"],
                "critical_fact_errors": [],
            }
        )
    with pytest.raises(ValidationError):
        parse_judge_decision(
            {
                "score": 0.8,
                "passed": True,
                "reasons": ["多余字段"],
                "critical_fact_errors": [],
                "unexpected": True,
            }
        )
