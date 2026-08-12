"""构建一次 Context，并打印审计信息与全部对照实验。"""

import json

from context_lab.builder import ContextBuilder
from context_lab.diagnostics import diagnose_build
from context_lab.experiments import run_all_experiments, sample_items
from context_lab.models import BuildRequest


def main() -> None:
    result = ContextBuilder(max_item_tokens=40).build(
        BuildRequest(
            task="定义成功率",
            tenant="tenant-a",
            roles={"analyst"},
            token_budget=240,
            reserved_tokens=30,
            layer_budgets={"retrieved": 90, "memory": 50},
            items=sample_items(),
        )
    )
    print("最终 Context：\n", result.context)
    print("\nManifest：\n", json.dumps(result.manifest.model_dump(), ensure_ascii=False, indent=2))
    print("\n裁剪诊断：\n", diagnose_build(result.manifest).model_dump_json(indent=2))
    print("\n对照实验：\n", json.dumps(run_all_experiments(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
