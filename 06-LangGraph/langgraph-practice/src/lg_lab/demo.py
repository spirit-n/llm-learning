"""展示 interrupt 和 resume 必须使用相同 thread_id。"""

from langgraph.types import Command

from lg_lab.graph import build_graph


def main() -> None:
    graph = build_graph()
    config = {"configurable": {"thread_id": "demo-order-001"}}

    paused = graph.invoke({"question": "查询昨天收入"}, config=config)
    print("首次调用已暂停：", paused["__interrupt__"][0].value)

    completed = graph.invoke(Command(resume=True), config=config)
    print("恢复后的答案：", completed["answer"])
    print("最终状态：", completed["status"])
    print("SQL 指纹：", completed["sql_fingerprint"])
    print("执行轨迹：", " → ".join(completed["trace"]))


if __name__ == "__main__":
    main()
