# LangGraph 从状态图到可恢复 Agent

## 1. 先画状态，再写代码

对指标 Agent 定义：输入问题、用户身份、检索到的 schema、SQL、guard 结果、查询结果、错误类型、重试次数和最终答案。不要把所有内容塞进一个 `messages` 列表。

```python
from typing import TypedDict

class AgentState(TypedDict, total=False):
    question: str
    user_id: str
    schemas: list[dict]
    sql: str
    guard_status: str
    rows: list[dict]
    error_code: str
    retry_count: int
    answer: str
```

## 2. 最小确定性图

```python
from langgraph.graph import StateGraph, START, END

def validate_question(state: AgentState):
    question = state["question"].strip()
    if not question:
        return {"error_code": "EMPTY_QUESTION"}
    return {}

def route_after_validate(state: AgentState):
    return "reject" if state.get("error_code") else "retrieve_schema"

builder = StateGraph(AgentState)
builder.add_node("validate", validate_question)
builder.add_node("retrieve_schema", retrieve_schema)  # 自己实现并测试
builder.add_node("reject", reject)
builder.add_edge(START, "validate")
builder.add_conditional_edges(
    "validate",
    route_after_validate,
    {"reject": "reject", "retrieve_schema": "retrieve_schema"},
)
builder.add_edge("reject", END)
```

代码只是示意；按当前官方 API 验证。先用纯函数节点和 fake 数据跑通，再加入模型和数据库。

## 3. 哪些节点用 LLM

- LLM 候选：意图分类、schema 选择辅助、SQL 草稿、结果解释。
- 确定性代码：权限、SQL AST、重试计数、成本上限、schema 校验、最终引用存在性。
- 人工：高风险动作、低置信度、合规要求或不可逆副作用。

## 4. Checkpoint 的意义

checkpoint 保存每一步状态，使进程崩溃或人工暂停后能继续。它还支持查看历史状态和调试，但不等于长期用户记忆。生产中选择 SQLite/Postgres 等持久化实现，并设计 thread/task ID、TTL、隐私和迁移。

## 5. Human-in-the-loop

在 SQL 执行前创建 interrupt，展示 SQL、表、扫描估计和原因。用户批准后 resume；拒绝则进入结束或修订路径。恢复时不能重复执行已经发生的副作用，因此节点必须考虑幂等。

## 6. 重试不是画一条回边

状态中记录 `error_code` 和 `retry_count`：语法错误可让模型修复；权限拒绝不应重试；数据库超时可缩小范围或一次退避；未知错误进入人工/失败。任何路径都有最大次数和结束状态。

## 7. 测试

- 单节点输入/输出测试。
- 路由表参数化测试。
- 从每个 checkpoint 恢复测试。
- 相同副作用节点重复执行的幂等测试。
- 状态 schema 版本迁移测试。
- 最大循环步数与超时测试。

## 8. 学完标准

你应能在白板上画图，说明每个状态字段由谁产生、哪些路径可达、在哪里验证、怎样退出和怎样恢复，而不只是展示 `graph.invoke()` 成功。
