import sys
from pathlib import Path

import pytest

from rag_lab.context import build_context, validate_citations
from rag_lab.pipeline import build_demo_pipeline


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from shared.live_llm import (  # noqa: E402
    LiveLLMSettings,
    OpenAICompatibleChatClient,
)


pytestmark = pytest.mark.live


def test_live_model_answers_only_from_retrieved_context():
    settings = LiveLLMSettings.from_env()

    question = "错误码 E102 是什么，应该怎样处理？"
    hits = build_demo_pipeline().retrieve(question, strategy="rerank", top_k=3)
    context, citation_ids = build_context(hits)
    assert citation_ids

    message = OpenAICompatibleChatClient(settings).chat(
        [
            {
                "role": "system",
                "content": (
                    "你是 RAG 回答器。只能使用给定证据；每个事实必须引用形如 [chunk-id] 的来源；"
                    "证据不足就明确说不知道，不得编造。"
                ),
            },
            {"role": "user", "content": f"问题：{question}\n\n证据：\n{context}"},
        ]
    )
    answer = message.get("content", "")
    assert answer.strip()
    # 不能只检查“包含任意一个合法引用”；同时出现伪造 ID 也必须失败。
    citation_check = validate_citations(answer, citation_ids)
    assert citation_check.valid, citation_check
