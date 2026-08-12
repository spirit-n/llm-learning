import json
import sys
from dataclasses import asdict
from pathlib import Path

import pytest

from skill_lab.catalog import discover_skill, load_instructions


REPO_ROOT = Path(__file__).resolve().parents[3]
SKILL_DIR = REPO_ROOT / "11-Agent-Skills" / "clickhouse-sql-review"
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(SKILL_DIR / "scripts"))

from shared.live_llm import (  # noqa: E402
    LiveLLMSettings,
    OpenAICompatibleChatClient,
    parse_json_content,
)
from validate_sql import validate_sql  # noqa: E402


pytestmark = pytest.mark.live


def test_live_model_explains_but_cannot_override_the_skill_validator():
    settings = LiveLLMSettings.from_env()

    sql = "SELECT * FROM analytics.orders LIMIT 2000"
    deterministic = validate_sql(sql, tenant="tenant-a", environment="prod")
    assert deterministic.decision == "reject"
    instructions = load_instructions(discover_skill(SKILL_DIR))

    message = OpenAICompatibleChatClient(settings).chat(
        [
            {
                "role": "system",
                "content": (
                    "你正在执行下面的 SQL review Skill。代码校验结果是不可覆盖的安全边界。"
                    "只输出 JSON，字段为 decision、reason_codes、explanation、suggested_fix。\n\n"
                    + instructions
                ),
            },
            {
                "role": "user",
                "content": (
                    f"SQL:\n{sql}\n\n"
                    f"确定性校验结果：{json.dumps(asdict(deterministic), ensure_ascii=False)}"
                ),
            },
        ]
    )
    output = parse_json_content(message)
    assert output["decision"] == "reject"
    assert set(deterministic.reason_codes).issubset(output["reason_codes"])
    assert output["explanation"].strip()
    assert output["suggested_fix"]
