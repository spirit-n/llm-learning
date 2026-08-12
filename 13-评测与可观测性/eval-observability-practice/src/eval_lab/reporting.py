from __future__ import annotations

import json
import re
from pathlib import Path

from .models import EvalReport
from .tracing import redact


SAFE_NAME = re.compile(r"[^a-zA-Z0-9_.-]+")


def write_report(report: EvalReport, output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    variant = SAFE_NAME.sub("-", str(redact(report.variant))).strip("-.") or "unknown"
    stem = f"{variant}-{report.run_id[:12]}"
    json_path = output_dir / f"{stem}.json"
    markdown_path = output_dir / f"{stem}.md"
    traces_path = output_dir / f"{stem}.traces.jsonl"

    # 注意：内存里的原始 trace 供即时评分；任何落盘 artifact 都必须先走同一套递归脱敏。
    # run_id 进入文件名，基线和候选的历史结果不会被下一次实验覆盖。
    safe_report = redact(report.model_dump(mode="json"))
    safe_traces = [redact(result.trace.model_dump(mode="json")) for result in report.results]
    _atomic_write(json_path, json.dumps(safe_report, ensure_ascii=False, indent=2))
    _atomic_write(
        traces_path,
        "\n".join(json.dumps(trace, ensure_ascii=False, separators=(",", ":")) for trace in safe_traces) + "\n",
    )

    metric_rows = "\n".join(f"| {name} | {value} |" for name, value in report.metrics.items())
    tag_rows = "\n".join(
        (
            f"| {redact(tag)} | {int(values['samples'])} | {values['goal_success']} | "
            f"{values['goal_success_ci_low']}～{values['goal_success_ci_high']} | "
            f"{values['safety']} | {values['system_error_rate']} |"
        )
        for tag, values in report.by_tag.items()
    )
    failure_rows = "\n".join(
        (
            f"| {redact(result.case.id)} | {redact(', '.join(result.case.tags))} | "
            f"{redact(', '.join(result.failure_reasons))} | {redact(result.trace.error_code or '-')} |"
        )
        for result in report.results
        if result.failure_reasons
    ) or "| - | - | none | - |"
    markdown = (
        f"# Eval Report: {redact(report.variant)}\n\n"
        f"- Run ID: `{report.run_id}`\n"
        f"- System version: `{redact(report.system_version)}`\n"
        f"- Dataset fingerprint: `{report.dataset_fingerprint}`\n"
        f"- Dataset size: {report.dataset_size}\n"
        f"- Failed cases: {redact(', '.join(report.failures)) or 'none'}\n"
        f"- Raw traces: `{traces_path.name}`\n\n"
        "## Metrics\n\n| Metric | Value |\n|---|---:|\n"
        f"{metric_rows}\n\n"
        "## Tag slices\n\n"
        "| Tag | Samples | Goal success | 95% CI | Safety | System error |\n"
        "|---|---:|---:|---:|---:|---:|\n"
        f"{tag_rows}\n\n"
        "## Failures\n\n"
        "| Case | Tags | Failed components | Error code |\n"
        "|---|---|---|---|\n"
        f"{failure_rows}\n"
    )
    _atomic_write(markdown_path, markdown)
    return json_path, markdown_path


def _atomic_write(path: Path, content: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)
