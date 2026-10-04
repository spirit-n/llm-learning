# 06｜LangGraph 与 Agent 工作流

2026-10 补充：[SQLite 跨进程恢复实验](./langgraph-practice/README.md#2026-10sqlite-跨进程恢复) 将内存 checkpoint 与持久化、幂等执行分开验证；原来的内存 Demo 保留。

**安排：** 第 4 周后 4 天，P0，第二重点。

详细学习：[LangGraph 从状态图到可恢复 Agent](./01-LangGraph入门实操.md)。

框架无关的 Agent 设计补充：[Microsoft AI Agents for Beginners 中文导读](./02-微软AI-Agents教程导读.md)。

配套工程：[langgraph-practice](./langgraph-practice/README.md)。默认流程用离线、确定性的 SQL 问答演示 StateGraph/reducer、条件路由、checkpoint、stream、interrupt/resume、错误分类、有限重试、幂等和结果验证；`tests_live/` 再把真实模型接到 SQL 生成节点前。

快速开始：

```powershell
cd 06-LangGraph/langgraph-practice
python -m pip install -e ".[dev]"
python -m lg_lab.demo
python -m pytest -q
```

## 零基础前置

先理解 Function Calling 和 LangChain 的 Tool；Python 方面会 dict、函数、`if/else` 和类型标注即可。把 State 想成“任务档案袋”、Node 想成“处理档案的一道工序”、Edge 想成“下一站指示牌”，再进入代码。

## 核心模型

- **State**：任务当前快照，字段要可解释、可序列化。
- **Node**：确定性代码、LLM、检索或工具步骤。
- **Edge**：固定流转；Conditional Edge 表达受控分支。
- **Checkpoint**：保存状态，使失败后恢复、人工介入和长任务成为可能。

## 项目图

```text
validate → classify → retrieve_schema → generate_sql → sql_guard
                                                   ├─ reject → answer
                                                   └─ human_review → execute
execute ──瞬时失败且有预算──→ execute
        ├─失败/耗尽────────→ answer
        └─成功────────────→ verify → answer
```

## 必做

- TypedDict/Pydantic state、reducer 基础。
- Node、Edge、conditional routing、subgraph。
- ToolNode 与受限 agent loop。
- checkpoint、thread/session、interrupt/resume。
- streaming、错误分类、重试预算、状态迁移测试。
- Human-in-the-loop：高风险或低置信度 SQL 在执行前确认。

## 为什么不是 `while True`

图把可达路径、状态变化、退出条件和人工确认点显式化，更容易测试、追踪、恢复和审计。简单的一步工具调用仍可使用有限循环，不必强行上图。

## 验收问题

- 哪些节点必须 deterministic？为什么 SQL guard 不能交给同一个 LLM 自审？
- checkpoint 与“聊天记录”有什么不同？
- 节点重试怎样保证副作用幂等？
- 如何防止图循环、状态无限增长和错误反复反馈？

## 资料怎么用

| 阶段/优先级 | 资料 | 它是干什么的 | 零基础怎么使用 |
|---|---|---|---|
| 建立直觉/P1 | [B站核心组件教程](https://www.bilibili.com/video/BV1wsoiYQENQ/) | 中文讲解 Graph、State、Node、Edge、checkpoint、HITL 和多 Agent | 先看前 5～8 节并画图，不要复制全部项目。视频中的导入路径和 API 要回官方文档核对 |
| 建立直觉/P1 | [DeepLearning.AI LangGraph](https://www.deeplearning.ai/courses/ai-agents-in-langgraph) | 用约 1.5 小时从手写 Agent 过渡到 LangGraph，并介绍 persistence 与 human-in-the-loop | 已理解 Function Calling 后看。重点是“为什么图更可控”，不是记住 essay writer 案例 |
| P0 | [LangGraph Overview](https://docs.langchain.com/oss/python/langgraph/overview) | 官方定位和快速入口，解释 durable execution、streaming、memory、HITL | 先读 Overview 和第一个最小图，确认 LangGraph 是编排运行时，不负责替你写 prompt 或业务规则 |
| P0 | [Graph API](https://docs.langchain.com/oss/python/langgraph/graph-api) | 详细解释 State、Node、Edge、reducer、编译和执行等核心概念 | 配合本目录实操逐节查。先掌握 State/Node/Edge/Conditional Edge，reducer 和 subgraph 后补 |
| 查字典 | [LangGraph API Reference](https://reference.langchain.com/python/langgraph/overview) | 精确查询包、类、函数和参数 | 代码导入或参数报错时使用，不适合零基础通读 |
| P0～P2 | [Microsoft AI Agents for Beginners（简体中文入口）](https://github.com/microsoft/ai-agents-for-beginners/blob/main/translations/zh-CN/README.md) | 微软的 Agent 设计课程，覆盖工具、规划、RAG、可信、多 Agent、协议、Context、记忆、生产与安全 | 先读概念；当前代码主线依赖 Microsoft Agent Framework/Foundry，不要求全部运行，按本目录导读映射到 LangGraph 项目 |

先画一个只有 3 个节点的纯 Python 图，再接模型、数据库和 checkpoint。一次加入所有能力会让错误无法定位。
