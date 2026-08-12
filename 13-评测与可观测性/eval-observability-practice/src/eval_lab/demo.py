from __future__ import annotations

import argparse
from pathlib import Path

from .app import DemoMetricAgent
from .dataset import load_dataset
from .reporting import write_report
from .runner import EvalRunner, evaluate_regression_gate


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATASET = PROJECT_ROOT / "evals" / "datasets" / "metric_agent_v1.jsonl"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    cases = load_dataset(DEFAULT_DATASET)
    runner = EvalRunner()
    baseline = runner.run(DemoMetricAgent("baseline"), cases)
    candidate = runner.run(DemoMetricAgent("candidate"), cases)
    print("baseline:", baseline.metrics)
    print("candidate:", candidate.metrics)
    gate = evaluate_regression_gate(baseline, candidate)
    print("regression gate:", gate.model_dump())
    if args.output_dir:
        print("reports:", write_report(baseline, args.output_dir), write_report(candidate, args.output_dir))


if __name__ == "__main__":
    main()
