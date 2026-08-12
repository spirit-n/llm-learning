"""定义并编译工作流图。"""

from functools import partial

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from lg_lab.nodes import (
    after_classify,
    after_execute,
    after_guard,
    after_review,
    after_schema,
    after_validate,
    after_verify,
    answer,
    classify,
    draft_sql,
    execute,
    human_review,
    retrieve_schema,
    sql_guard,
    validate,
    verify_result,
)
from lg_lab.state import WorkflowState
from lg_lab.warehouse import DemoWarehouse, Warehouse


def build_graph(checkpointer=None, *, warehouse: Warehouse | None = None):
    warehouse = warehouse or DemoWarehouse()
    builder = StateGraph(WorkflowState)
    builder.add_node("validate", validate)
    builder.add_node("classify", classify)
    builder.add_node("schema", retrieve_schema)
    builder.add_node("draft_sql", draft_sql)
    builder.add_node("guard", sql_guard)
    builder.add_node("review", human_review)
    # 外部依赖由图工厂注入；checkpoint 中只保存状态，不序列化数据库连接。
    builder.add_node("execute", partial(execute, warehouse=warehouse))
    builder.add_node("verify", verify_result)
    builder.add_node("answer", answer)

    builder.add_edge(START, "validate")
    builder.add_conditional_edges("validate", after_validate, {"classify": "classify", "answer": "answer"})
    builder.add_conditional_edges("classify", after_classify, {"schema": "schema", "answer": "answer"})
    builder.add_conditional_edges("schema", after_schema, {"draft_sql": "draft_sql", "answer": "answer"})
    builder.add_edge("draft_sql", "guard")
    builder.add_conditional_edges("guard", after_guard, {"review": "review", "answer": "answer"})
    builder.add_conditional_edges("review", after_review, {"execute": "execute", "answer": "answer"})
    builder.add_conditional_edges(
        "execute",
        after_execute,
        {"retry": "execute", "verify": "verify", "answer": "answer"},
    )
    builder.add_conditional_edges("verify", after_verify, {"answer": "answer"})
    builder.add_edge("answer", END)
    return builder.compile(checkpointer=checkpointer or InMemorySaver())
