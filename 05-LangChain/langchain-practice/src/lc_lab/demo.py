"""依次展示 LangChain 的几个核心抽象。"""

from lc_lab.agent import ask_metric
from lc_lab.retriever import demo_retriever
from lc_lab.runnables import intent_chain, request_pipeline, word_stream
from lc_lab.runtime import run_metric_agent
from lc_lab.structured import parse_intent, prompt
from lc_lab.tools import get_metric_definition


def main() -> None:
    print("工具 schema：", get_metric_definition.args_schema.model_json_schema())
    print("Agent：", ask_metric("成功率的正式定义是什么？"))
    print("受控运行结果：", run_metric_agent("收入怎么定义？").model_dump())
    print("Prompt：", prompt.invoke({"question": "查昨天收入"}).messages)
    print("结构化结果：", parse_intent('{"category":"data_query","reason":"需要查询数据"}'))
    print("检索结果：", demo_retriever().invoke("revenue refunds"))
    print("Runnable 分支：", intent_chain.invoke(" 查询 Revenue "))
    print("Runnable 请求管道：", request_pipeline.invoke(" 查询 Revenue "))
    print("Streaming：", "".join(word_stream.stream("one token at a time")))


if __name__ == "__main__":
    main()
