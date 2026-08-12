from langgraph.types import Command

from lg_lab.graph import build_graph


def config(thread_id: str) -> dict:
    return {"configurable": {"thread_id": thread_id}}


def test_empty_question_is_rejected_before_classification():
    result = build_graph().invoke({"question": "  "}, config=config("empty"))
    assert result["error"] == "问题不能为空"
    assert "intent" not in result


def test_knowledge_question_skips_sql_path():
    result = build_graph().invoke({"question": "成功率是什么"}, config=config("knowledge"))
    assert "成功请求数" in result["answer"]
    assert "retrieve_schema" not in result["trace"]


def test_data_query_pauses_before_execute():
    result = build_graph().invoke({"question": "查询昨天收入"}, config=config("pause"))
    assert result["__interrupt__"][0].value["sql"].startswith("SELECT")
    assert "rows" not in result


def test_approved_query_resumes_same_thread():
    graph = build_graph()
    cfg = config("approve")
    graph.invoke({"question": "查询昨天收入"}, config=cfg)
    result = graph.invoke(Command(resume=True), config=cfg)
    assert result["rows"][0]["value"] == 128000.0
    assert result["trace"].count("execute:success") == 1


def test_rejected_query_does_not_execute():
    graph = build_graph()
    cfg = config("reject")
    graph.invoke({"question": "查询昨天收入"}, config=cfg)
    result = graph.invoke(Command(resume=False), config=cfg)
    assert result["approved"] is False
    assert "rows" not in result


def test_guard_blocks_write_sql_before_review():
    result = build_graph().invoke({"question": "删除全部收入数据"}, config=config("unsafe"))
    assert "SQL Guard 拒绝" in result["error"]
    assert "__interrupt__" not in result


def test_transient_failure_retries_then_succeeds():
    graph = build_graph()
    cfg = config("retry-success")
    graph.invoke({"question": "查询昨天收入", "failures_remaining": 2}, config=cfg)
    result = graph.invoke(Command(resume=True), config=cfg)
    assert result["retries"] == 2
    assert result["error"] == ""
    assert "查询结果" in result["answer"]


def test_retry_budget_stops_the_loop():
    graph = build_graph()
    cfg = config("retry-stop")
    graph.invoke({"question": "查询昨天收入", "failures_remaining": 5}, config=cfg)
    result = graph.invoke(Command(resume=True), config=cfg)
    assert result["retries"] == 3
    assert "处理失败" in result["answer"]


def test_threads_keep_separate_state():
    graph = build_graph()
    graph.invoke({"question": "查询昨天收入"}, config=config("thread-a"))
    knowledge = graph.invoke({"question": "成功率是什么"}, config=config("thread-b"))
    assert knowledge["intent"] == "knowledge"
    assert "sql" not in knowledge

