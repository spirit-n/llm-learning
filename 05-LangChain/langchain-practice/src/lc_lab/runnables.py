"""Runnable 组合、条件分支和 streaming 示例。"""

from collections.abc import Iterator
from typing import TypedDict

from langchain_core.runnables import RunnableBranch, RunnableLambda


normalize = RunnableLambda(lambda text: text.strip().lower())
route = RunnableBranch(
    (lambda text: "收入" in text or "revenue" in text, lambda _: "data_query"),
    lambda _: "knowledge",
)
intent_chain = normalize | route


class PreparedRequest(TypedDict):
    normalized_question: str
    route: str
    char_count: int


def prepare_request(text: str) -> PreparedRequest:
    normalized_text = normalize.invoke(text)
    return {
        "normalized_question": normalized_text,
        "route": route.invoke(normalized_text),
        "char_count": len(normalized_text),
    }


# Runnable 可以是应用边界的一部分，但输入校验/权限仍应放在确定性函数中。
request_pipeline = RunnableLambda(prepare_request)


def stream_words(text: str) -> Iterator[str]:
    for word in text.split():
        yield word + " "


word_stream = RunnableLambda(stream_words)
