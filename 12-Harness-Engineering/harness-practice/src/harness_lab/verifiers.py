from __future__ import annotations

import math

from .models import Observation, TaskSpec, Verification


def verify_metric_answer(task: TaskSpec, answer: str, observations: list[Observation]) -> Verification:
    if not task.expected_metric:
        return Verification(passed=False, code="VERIFICATION_TARGET_MISSING", message="任务没有声明 expected_metric")
    if not answer.strip():
        return Verification(passed=False, code="EMPTY_ANSWER", message="答案为空")
    rows = []
    for observation in observations:
        if observation.status != "ok" or not isinstance(observation.data, dict):
            continue
        raw_rows = observation.data.get("rows")
        if raw_rows is None:
            continue
        if not isinstance(raw_rows, list):
            return Verification(passed=False, code="RESULT_SCHEMA_INVALID", message="rows 必须是数组")
        rows.extend(raw_rows)
    if not rows:
        return Verification(passed=False, code="EMPTY_RESULT", message="没有可验证的数据行")
    # 所有指标行都必须有明确的指标名和有限数值。空 values 不能被当成“验证通过”。
    if any(
        not isinstance(row, dict)
        or not isinstance(row.get("metric"), str)
        or not row["metric"].strip()
        or isinstance(row.get("value"), bool)
        or not isinstance(row.get("value"), (int, float))
        or not math.isfinite(row["value"])
        for row in rows
    ):
        return Verification(passed=False, code="RESULT_SCHEMA_INVALID", message="指标行缺少合法 metric/value")
    values = [row["value"] for row in rows]
    if any(row["metric"] != task.expected_metric for row in rows):
        return Verification(passed=False, code="METRIC_MISMATCH", message="工具结果与任务验收指标不一致")
    if any(value < 0 or value > 1 for value in values):
        return Verification(passed=False, code="RESULT_ANOMALY", message="成功率超出 0～1")
    expected_fragments = {
        str(round(value * 100, 2)).rstrip("0").rstrip(".")
        for value in values
    }
    # 多行结果必须逐个可在答案中核对；只命中其中一个值不能算完成验收。
    if any(fragment not in answer for fragment in expected_fragments):
        return Verification(passed=False, code="ANSWER_MISMATCH", message="答案与工具结果不一致")
    return Verification(passed=True, code="VERIFIED", message="确定性验证通过")
