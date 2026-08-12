import sys
from pathlib import Path

import pytest

from context_lab.builder import ContextBuilder
from context_lab.experiments import sample_items
from context_lab.models import BuildRequest


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from shared.live_llm import (  # noqa: E402
    LiveLLMSettings,
    OpenAICompatibleChatClient,
    parse_json_content,
)


pytestmark = pytest.mark.live


def test_live_model_uses_the_selected_context_and_reports_source_ids():
    settings = LiveLLMSettings.from_env()

    built = ContextBuilder(min_relevance=0.3).build(
        BuildRequest(
            task="回答成功率定义并引用来源",
            tenant="tenant-a",
            roles={"analyst"},
            token_budget=300,
            items=sample_items(),
        )
    )
    included_ids = [entry.id for entry in built.manifest.included]
    assert "metric-new" in included_ids
    assert "metric-old" not in included_ids

    message = OpenAICompatibleChatClient(settings).chat(
        [
            {
                "role": "system",
                "content": (
                    "只能根据 CONTEXT 回答。严格输出 JSON："
                    '{"answer":"...","source_ids":["..."]}；source_ids 只能从给定 ID 选择。'
                ),
            },
            {
                "role": "user",
                "content": (
                    f"允许的 source_ids: {included_ids}\n"
                    f"CONTEXT:\n{built.context}\n\n问题：成功率是什么？"
                ),
            },
        ]
    )
    output = parse_json_content(message)
    assert "成功请求数" in output["answer"]
    assert "总请求数" in output["answer"]
    assert "metric-new" in output["source_ids"]
    assert set(output["source_ids"]).issubset(included_ids)
