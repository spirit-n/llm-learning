"""演示目录发现、progressive disclosure 与一次确定性 SQL 评审。"""

import importlib.util
import json
import sys
from dataclasses import asdict
from pathlib import Path

from skill_lab.catalog import SkillCatalog, SkillLoader, validate_skill_package


SKILL_ROOT = Path(__file__).resolve().parents[3]
SKILL_DIR = SKILL_ROOT / "clickhouse-sql-review"


def load_validator(path: Path):
    spec = importlib.util.spec_from_file_location("clickhouse_validator", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.validate_sql


def main() -> None:
    catalog = SkillCatalog.from_root(SKILL_ROOT)
    loader = SkillLoader(catalog)
    task = "执行前检查这条 ClickHouse SQL 是否安全"
    matches = catalog.match(task)
    print("启动时发现：", [value.name for value in catalog.snapshot.skills])
    print("发现阶段只读取 frontmatter 字节：", catalog.snapshot.frontmatter_bytes_read)
    print("任务命中：", [value.name for value in matches])

    # 只有任务命中后才加载正文，只有确实要解释权限时才加载对应 reference。
    loader.load_instructions("clickhouse-sql-review")
    loader.load_reference("clickhouse-sql-review", "references/sensitive-columns.md")
    validator_path = loader.resolve_script("clickhouse-sql-review", "scripts/validate_sql.py")
    result = load_validator(validator_path)(
        "SELECT day, revenue FROM analytics.daily_metrics LIMIT 100",
        "tenant-a",
        "revenue",
        "dev",
    )
    print("评审结果：", json.dumps(asdict(result), ensure_ascii=False, indent=2))
    print("渐进加载审计：", json.dumps([asdict(event) for event in loader.events], ensure_ascii=False, indent=2))
    package = validate_skill_package(SKILL_DIR)
    print("Skill 包静态验收：", json.dumps(asdict(package), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
