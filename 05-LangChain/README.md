# 05｜LangChain

**安排：** 第 4 周第 1～2 天，P1。学“当前核心抽象与集成”，不通读框架。

详细学习：[LangChain 零基础入门与边界](./01-LangChain入门实操.md)。

微软课程导读：[Microsoft LangChain for Beginners 中文学习路线](./02-微软LangChain教程导读.md)。

## 零基础前置

必须先手写过一次普通模型请求或 fake tool loop，否则框架抽象会显得像魔法。需要会 Python 函数、装包、import、异常和 Pydantic；类只需看懂构造与方法，不要求精通面向对象。

## 要掌握

- model、message、prompt/template、structured output。
- tool、tool runtime、agent loop 与 middleware。
- document loader、splitter、embedding、vector store、retriever。
- runnable/streaming 的基本组合与回调/trace。

## 学习方法

1. 先手写一次 model call、tool loop 和 RAG pipeline。
2. 再用 LangChain 替换重复的模型/工具/检索器适配代码。
3. 对比框架带来的收益与隐性成本：依赖、抽象泄漏、调试和版本变化。

## 不必深挖

- 历史版本的所有 Chain、旧 memory 教程、每个向量库 connector。
- 为了“用了 LangChain”而把确定性业务逻辑包装成 LLM chain。

## 验收

- 可切换两个模型 provider，而业务层不改或少改。
- 工具 schema、错误处理和 streaming 有测试。
- 能解释 LangChain 与 LangGraph：前者提供高层 agent/组件抽象，后者侧重可控的状态化编排运行时；LangGraph 可独立使用。

## 资料怎么用

| 优先级 | 资料 | 它是干什么的 | 零基础怎么使用 |
|---|---|---|---|
| P0 | [LangChain Overview](https://docs.langchain.com/oss/python/langchain/overview) | 官方总览，解释 LangChain 当前的 model、tool、agent 和 middleware 等核心抽象 | 第 4 周先读 Overview/Quickstart。每出现一个名词，就回到自己的手写版本找对应部分，不要连续跳十层链接 |
| 查字典 | [LangChain API Reference](https://reference.langchain.com/python/) | 查询类、函数、参数、返回类型和导入路径的技术字典 | 写代码报“参数不存在/导入失败”时查。它不是教材，不要从第一页往后读 |
| P1 | [LangChain Academy](https://academy.langchain.com/) | 官方课程平台，提供 LangChain、LangGraph、LangSmith 等分阶段课程和练习 | 先选 Introduction/Essentials 级别课程；一次只学与本周项目相关的一门，课程代码仍要对照当前文档 |
| P0/P1 | [Microsoft LangChain for Beginners](https://github.com/microsoft/langchain-for-beginners) | 微软的 9 章 Python 入门课程，从环境、模型、消息、工具到 MCP、语义检索和 Agentic RAG | 不要连续通刷；按本目录导读分散到第 1～6 周，并把示例改成自己的指标/RAG 场景 |

判断是否学会的标准不是“看完课程”，而是能在不用 LangChain 时手写最小流程，并说明使用框架减少了哪些适配代码。
