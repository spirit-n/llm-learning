from __future__ import annotations

import math
import time
from collections import defaultdict
from statistics import mean
from typing import Protocol
from uuid import uuid4

from .dataset import dataset_fingerprint
from .evaluators import evaluate
from .models import (
    AgentTrace,
    CaseResult,
    EvalCase,
    EvalInput,
    EvalReport,
    GateResult,
    RegressionPolicy,
)


METRICS = (
    "behavior",
    "answer",
    "tool_selection",
    "tool_execution",
    "arguments",
    "trajectory",
    "trace_quality",
    "evidence",
    "safety",
    "system_ok",
    "goal_success",
)


class EvaluatedSystem(Protocol):
    variant: str
    system_version: str

    def run(self, request: EvalInput) -> AgentTrace: ...


class TraceContractError(ValueError):
    """被测系统返回了无法归属于当前样本/版本的 trace。"""


class EvalRunner:
    def run(self, agent: EvaluatedSystem, cases: list[EvalCase]) -> EvalReport:
        if not cases:
            raise ValueError("评测集不能为空")
        variant = self._required_identity(agent, "variant")
        system_version = self._required_identity(agent, "system_version")
        # Runner 也必须防御绕过 load_dataset() 的调用方：重新验证并快照 oracle，
        # 使并发修改或 model_construct() 不能在评测途中改变评分标准。
        cases = [
            EvalCase.model_validate(case.model_dump(mode="python", warnings=False))
            if isinstance(case, EvalCase)
            else EvalCase.model_validate(case)
            for case in cases
        ]
        case_ids = [case.id for case in cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("评测集 case id 重复")
        run_id = uuid4().hex
        results: list[CaseResult] = []
        seen_trace_ids: set[str] = set()
        for case in cases:
            started = time.perf_counter()
            try:
                # 关键隔离边界：系统只能看到公开输入，不能读到 expected_answer、
                # forbidden_tools 等 oracle，也就不能通过篡改 EvalCase 影响评分。
                request = EvalInput(case_id=case.id, user_input=case.input)
                raw_trace = agent.run(request)
                elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
                # 对已经是 AgentTrace 的实例也重新从 dict 校验，不能被 model_construct/
                # model_copy(update=...) 绕过字段约束。
                trace_payload = raw_trace.model_dump(mode="python") if isinstance(raw_trace, AgentTrace) else raw_trace
                trace = AgentTrace.model_validate(trace_payload)
                self._validate_trace_identity(variant, system_version, case, trace)
                if trace.trace_id in seen_trace_ids:
                    raise TraceContractError("trace_id 在同一批评测中重复")
                seen_trace_ids.add(trace.trace_id)
                # 延迟必须由 Harness 在调用边界外实测，不能相信被测系统自报的数字。
                trace = trace.model_copy(update={"latency_ms": elapsed_ms})
            except Exception as exc:
                # 单个系统错误必须保留成失败样本，不能让整批评测中断或悄悄丢样本。
                trace = AgentTrace(
                    trace_id=uuid4().hex,
                    case_id=case.id,
                    variant=variant,
                    status="error",
                    behavior="error",
                    output="",
                    latency_ms=round((time.perf_counter() - started) * 1000, 3),
                    prompt_tokens=0,
                    completion_tokens=0,
                    system_version=system_version,
                    error_code=type(exc).__name__,
                )
            scores, reasons = evaluate(case, trace)
            results.append(CaseResult(case=case, trace=trace, scores=scores, failure_reasons=reasons))

        return EvalReport(
            run_id=run_id,
            variant=variant,
            system_version=system_version,
            dataset_fingerprint=dataset_fingerprint(cases),
            dataset_size=len(results),
            metrics=self._aggregate(results),
            by_tag=self._by_tag(results),
            failures=[result.case.id for result in results if result.scores.goal_success == 0],
            results=results,
        )

    @staticmethod
    def _required_identity(agent: EvaluatedSystem, field: str) -> str:
        value = getattr(agent, field, None)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"被测系统 {field} 必须是非空字符串")
        return value

    @staticmethod
    def _validate_trace_identity(
        variant: str,
        system_version: str,
        case: EvalCase,
        trace: AgentTrace,
    ) -> None:
        """拒绝串样本、串版本的 trace，避免缓存污染制造假通过。"""
        mismatches: list[str] = []
        if trace.case_id != case.id:
            mismatches.append("case_id")
        if trace.variant != variant:
            mismatches.append("variant")
        if trace.system_version != system_version:
            mismatches.append("system_version")
        if mismatches:
            raise TraceContractError(f"trace 身份不匹配：{', '.join(mismatches)}")

    @staticmethod
    def _aggregate(results: list[CaseResult]) -> dict[str, float]:
        values = {name: round(mean(getattr(result.scores, name) for result in results), 4) for name in METRICS}
        total_weight = sum(result.case.weight for result in results)
        values["weighted_goal_success"] = round(
            sum(result.scores.goal_success * result.case.weight for result in results) / total_weight,
            4,
        )
        latencies = sorted(result.trace.latency_ms for result in results)
        values["latency_p50_ms"] = percentile(latencies, 0.50)
        values["latency_p95_ms"] = percentile(latencies, 0.95)
        values["avg_total_tokens"] = round(
            mean(result.trace.prompt_tokens + result.trace.completion_tokens for result in results),
            2,
        )
        values["total_estimated_cost_usd"] = round(sum(result.trace.estimated_cost_usd for result in results), 8)
        values["system_error_rate"] = round(mean(result.trace.status == "error" for result in results), 4)
        return values

    @staticmethod
    def _by_tag(results: list[CaseResult]) -> dict[str, dict[str, float]]:
        groups: dict[str, list[CaseResult]] = defaultdict(list)
        for result in results:
            for tag in result.case.tags:
                groups[tag].append(result)
        slices: dict[str, dict[str, float]] = {}
        for tag, items in sorted(groups.items()):
            successes = sum(item.scores.goal_success for item in items)
            low, high = wilson_interval(int(successes), len(items))
            slices[tag] = {
                "samples": float(len(items)),
                "goal_success": round(successes / len(items), 4),
                "goal_success_ci_low": low,
                "goal_success_ci_high": high,
                "safety": round(mean(item.scores.safety for item in items), 4),
                "system_error_rate": round(mean(item.trace.status == "error" for item in items), 4),
            }
        return slices


def percentile(sorted_values: list[float], quantile: float) -> float:
    if not sorted_values:
        return 0.0
    if not 0 <= quantile <= 1:
        raise ValueError("quantile 必须在 0～1")
    # 线性插值比 round(index) 稳定，尤其是教学用的小样本集。
    position = (len(sorted_values) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return round(sorted_values[lower], 3)
    fraction = position - lower
    return round(sorted_values[lower] + (sorted_values[upper] - sorted_values[lower]) * fraction, 3)


def wilson_interval(successes: int, total: int, z: float = 1.96) -> tuple[float, float]:
    if total <= 0:
        return 0.0, 0.0
    proportion = successes / total
    denominator = 1 + z**2 / total
    centre = (proportion + z**2 / (2 * total)) / denominator
    margin = z * math.sqrt((proportion * (1 - proportion) + z**2 / (4 * total)) / total) / denominator
    return round(max(0, centre - margin), 4), round(min(1, centre + margin), 4)


def evaluate_regression_gate(
    baseline: EvalReport,
    candidate: EvalReport,
    policy: RegressionPolicy | None = None,
) -> GateResult:
    policy = policy or RegressionPolicy()
    failures: list[str] = []
    metric_deltas = {
        name: round(candidate.metrics[name] - baseline.metrics[name], 4)
        for name in ("goal_success", "safety", "latency_p95_ms", "system_error_rate")
    }

    if baseline.dataset_fingerprint != candidate.dataset_fingerprint:
        failures.append("dataset_fingerprint_mismatch")
    if candidate.metrics["goal_success"] < policy.min_goal_success:
        failures.append("goal_success_below_minimum")
    if candidate.metrics["safety"] < policy.min_safety:
        failures.append("safety_below_minimum")
    if candidate.metrics["goal_success"] < baseline.metrics["goal_success"] - policy.max_goal_regression:
        failures.append("goal_success_regressed")
    if candidate.metrics["safety"] < baseline.metrics["safety"]:
        failures.append("safety_regressed")
    baseline_p95 = baseline.metrics["latency_p95_ms"]
    if baseline_p95 > 0 and candidate.metrics["latency_p95_ms"] > baseline_p95 * policy.max_p95_latency_ratio:
        failures.append("latency_p95_regressed")

    baseline_cases = {item.case.id: item for item in baseline.results}
    candidate_cases = {item.case.id: item for item in candidate.results}
    case_regressions = sorted(
        case_id
        for case_id in baseline_cases.keys() & candidate_cases.keys()
        if baseline_cases[case_id].scores.goal_success == 1 and candidate_cases[case_id].scores.goal_success == 0
    )
    case_improvements = sorted(
        case_id
        for case_id in baseline_cases.keys() & candidate_cases.keys()
        if baseline_cases[case_id].scores.goal_success == 0 and candidate_cases[case_id].scores.goal_success == 1
    )
    if len(case_regressions) > policy.allow_case_regressions:
        failures.append("case_level_regression")

    # 总平均值可能掩盖高风险小切片，所以 permission/safety 等标签必须单独不退化。
    for tag in policy.protected_tags:
        if tag in baseline.by_tag and tag in candidate.by_tag:
            if candidate.by_tag[tag]["goal_success"] < baseline.by_tag[tag]["goal_success"]:
                failures.append(f"protected_tag_regressed:{tag}")

    failures = list(dict.fromkeys(failures))
    return GateResult(
        passed=not failures,
        failures=failures,
        metric_deltas=metric_deltas,
        case_regressions=case_regressions,
        case_improvements=case_improvements,
    )


def regression_gate(baseline: EvalReport, candidate: EvalReport) -> list[str]:
    """保留简单调用接口；需要差异详情时使用 evaluate_regression_gate。"""
    return evaluate_regression_gate(baseline, candidate).failures
