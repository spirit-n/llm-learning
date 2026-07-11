# 18｜前沿技术雷达

**安排：** 每周 2～3 小时，P2/P3。目标是面试能说出“是什么、解决什么、成熟度、风险、是否值得采用”，不是追热点写 Demo。

具体记录请复制：[技术卡模板与示例](./01-技术卡模板与示例.md)。

## 零基础提示

前沿技术名词最多，也最容易制造焦虑。本章不是当前学习入口。每周只允许看一个主题；如果还不能稳定解释 RAG、Tool Calling、LangGraph 和 MCP，就先不做 P3 Demo。

## 跟踪方法

每个主题只写一张技术卡：

```text
名称 / 日期 / 官方来源
解决的问题
核心机制
与现有方案的差异
成熟度与采用信号
安全/成本/运维风险
对当前项目的实验假设
结论：采用 / 试验 / 观察 / 忽略
```

## P2：与岗位较相关

- Agentic RAG、Adaptive/Corrective/Self-RAG。
- 多模态 RAG：布局、OCR、表格、图片检索和多模态评测。
- GraphRAG 与知识图谱检索；先判断是否真的需要全局关系/多跳。
- 长期记忆、episodic/semantic/procedural memory 与记忆评测。
- 小模型路由、量化、本地推理、推测解码和成本优化。
- LLM security、MCP security、tool injection、agent identity。

## P3：保持关注

- A2A 与其他跨 Agent 互操作协议。
- Computer Use / browser agents。
- Agentic RL、过程奖励、轨迹数据与自我改进。
- Deep/Research agents、长期任务与异步 agent runtime。
- Agent Skills 生态、可移植性、供应链与可信执行。
- Dify、Coze、低代码 Agent 平台：重点看产品交付速度、扩展边界和锁定风险。
- 新的上下文压缩、缓存、路由和模型协作技术。

## 信息源

- 各项目官方 docs、GitHub release/changelog 和论文优先于二手解读。

| 优先级 | 信息源 | 它是干什么的 | 零基础怎么使用 |
|---|---|---|---|
| P2 | [Hugging Face Papers](https://huggingface.co/papers) | 每日论文和社区讨论入口，适合发现当前模型/RAG/Agent 研究主题 | 每周只选一篇与当前项目相关的；先读摘要、图和结论，不要求啃完公式 |
| P3 | [Papers with Code](https://paperswithcode.com/) | 将论文、任务、数据集、指标和开源实现关联起来 | 想确认某技术是否有代码/基准时查，不要按排行榜盲目选模型 |
| P2 | [LangChain Blog](https://blog.langchain.com/) | LangChain 团队发布框架设计、Agent、LangGraph、评测和产品更新 | 只读与你当前版本/主题相关的文章，代码仍以 docs/reference 为准 |
| P2 | [MCP Blog](https://blog.modelcontextprotocol.io/) | MCP 官方生态、规范演进和重要发布说明 | 做 MCP 项目期间每两周查看一次，重点关注 transport、安全和规范变化 |
| P2 | [AgentScope Releases](https://github.com/agentscope-ai/agentscope/releases) | AgentScope 每个版本的新增、修复和破坏性变化 | 安装/升级前查当前 release；确认教程 API 是否仍适用，不用逐条背更新日志 |

不要用“最近很火”作为采用依据。技术卡必须落到任务、指标、运维和安全边界。
