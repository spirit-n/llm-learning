import sys
from pathlib import Path

import pytest

from lg_lab.nodes import sql_guard


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from shared.live_llm import (  # noqa: E402
    LiveLLMSettings,
    OpenAICompatibleChatClient,
    parse_json_content,
)


pytestmark = pytest.mark.live


def test_live_model_drafts_sql_that_enters_deterministic_guard():
    settings = LiveLLMSettings.from_env()

    message = OpenAICompatibleChatClient(settings).chat(
        [
            {
                "role": "system",
                "content": (
                    "你是 LangGraph 中的 draft_sql 节点。只输出 JSON："
                    '{"intent":"data_query","sql":"..."}。SQL 必须是单条 SQLite SELECT，必须带 LIMIT。'
                ),
            },
            {
                "role": "user",
                "content": (
                    "schema: daily_metrics(day TEXT, revenue REAL, success_count INTEGER, request_count INTEGER)\n"
                    "question: 查询昨天的成功率"
                ),
            },
        ]
    )
    output = parse_json_content(message)
    assert output["intent"] == "data_query"
    state = {"sql": output["sql"], "trace": []}
    guarded = sql_guard(state)
    assert guarded["error"] == "", output
    assert guarded["trace"][-1] == "guard:passed"
