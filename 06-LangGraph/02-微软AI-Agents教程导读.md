# Microsoft AI Agents for Beginners 中文导读

- 主仓库：[microsoft/ai-agents-for-beginners](https://github.com/microsoft/ai-agents-for-beginners)
- [简体中文入口](https://github.com/microsoft/ai-agents-for-beginners/blob/main/translations/zh-CN/README.md)

这套课适合学习 Agent 的“设计问题”，不等于 LangGraph 教程。当前代码示例主线使用 Microsoft Agent Framework 与 Microsoft Foundry Agent Service V2，仓库说明 Foundry 路线需要 Azure 账号；部分示例可能支持其他兼容 provider。对你来说，先读概念/视频，再用 LangGraph 或 AgentScope 复现最重要的模式即可。

> 简体中文由自动翻译维护。概念学习可看中文，参数、安全规则和代码报错要回英文原文核对。

## 章节优先级与本计划映射

| 章节 | 核心问题 | 优先级/周次 | 结合本项目怎么学 |
|---|---|---|---|
| [00 Course Setup](https://github.com/microsoft/ai-agents-for-beginners/tree/main/00-course-setup) | 课程代码、模型/服务和环境如何配置 | P2/准备运行代码时 | 先读要求和费用/账号；不为概念学习强行配置 Azure |
| [01 Intro to AI Agents](https://github.com/microsoft/ai-agents-for-beginners/tree/main/01-intro-to-ai-agents) | 什么是 Agent、适用场景和基本组成 | P0/第 4 周 | 画出 Model + Instructions + Tools + State + Harness；写不适合 Agent 的场景 |
| [02 Agentic Frameworks](https://github.com/microsoft/ai-agents-for-beginners/tree/main/02-explore-agentic-frameworks) | 框架如何抽象模型、工具、状态和编排 | P1/第 4～5 周 | 用同一任务比较 LangChain/LangGraph/AgentScope，而非背框架名称 |
| [03 Design Patterns](https://github.com/microsoft/ai-agents-for-beginners/tree/main/03-agentic-design-patterns) | 常见 Agent 工作方式与模式选择 | P0/第 4 周 | 每种模式写输入、输出、停止条件和失败；只实现项目需要的模式 |
| [04 Tool Use](https://github.com/microsoft/ai-agents-for-beginners/tree/main/04-tool-use) | Agent 如何选择和调用外部工具 | P0/第 1/4 周 | 对照手写 tool loop；补权限、schema、timeout、最大步骤和审计 |
| [05 Agentic RAG](https://github.com/microsoft/ai-agents-for-beginners/tree/main/05-agentic-rag) | Agent 何时检索、如何把 RAG 作为工具 | P1/第 5 周 | 与固定 RAG 做 30 条对照，证明路由收益是否值得额外成本 |
| [06 Trustworthy Agents](https://github.com/microsoft/ai-agents-for-beginners/tree/main/06-building-trustworthy-agents) | 可靠、安全、透明和负责的 Agent | P0/第 6～7 周 | 转为权限、Guard、Verifier、trace、HITL 和安全测试清单 |
| [07 Planning](https://github.com/microsoft/ai-agents-for-beginners/tree/main/07-planning-design) | Agent 如何分解任务和规划步骤 | P1/第 4～6 周 | 限制计划长度、允许工具和预算；比较预定义图与动态规划 |
| [08 Multi-Agent](https://github.com/microsoft/ai-agents-for-beginners/tree/main/08-multi-agent) | 多 Agent 如何分工、协作、路由 | P2/第 5 周 | 优先用已掌握的 LangGraph 做单/多 Agent 对照；时间充足再用 AgentScope 复刻。Review Agent 不能替代确定性 Guard |
| [09 Metacognition](https://github.com/microsoft/ai-agents-for-beginners/tree/main/09-metacognition) | Agent 如何反思、监控和修正自身过程 | P2/第 5～7 周 | 将“自我反思”视为弱验证信号，与规则/独立证据/人工比较 |
| [10 Production](https://github.com/microsoft/ai-agents-for-beginners/tree/main/10-ai-agents-production) | Agent 上生产需要哪些运行与运维能力 | P0/第 7 周 | 映射 timeout、队列、checkpoint、成本、观测、故障与灰度 |
| [11 Agentic Protocols](https://github.com/microsoft/ai-agents-for-beginners/tree/main/11-agentic-protocols) | MCP、A2A、NLWeb 等互操作协议 | P1/第 6 周 | 重点比较 MCP/A2A 的通信对象、发现、状态与安全边界 |
| [12 Context Engineering](https://github.com/microsoft/ai-agents-for-beginners/tree/main/12-context-engineering) | 给 Agent 什么信息、如何选择/压缩/隔离 | P0/第 5 周 | 实现 context manifest 和 token 预算；做 schema/历史对照实验 |
| [13 Agent Memory](https://github.com/microsoft/ai-agents-for-beginners/tree/main/13-agent-memory) | 短期/长期记忆如何写入、检索和治理 | P1/第 5 周 | 区分聊天历史、任务状态和长期记忆；加入 TTL/删除/权限与评测 |
| [14 Microsoft Agent Framework](https://github.com/microsoft/ai-agents-for-beginners/tree/main/14-microsoft-agent-framework) | 微软 Agent Framework 的具体使用 | P2/按目标 JD | 只有岗位/项目需要微软栈时深入；否则理解框架对比即可 |
| [15 Browser Use](https://github.com/microsoft/ai-agents-for-beginners/tree/main/15-browser-use) | Agent 操作浏览器/计算机界面 | P3/第 8 周技术雷达 | 重点看动作权限、确认、网页注入、沙箱和可复现评测 |
| [18 Securing AI Agents](https://github.com/microsoft/ai-agents-for-beginners/tree/main/18-securing-ai-agents) | Agent 身份、工具、数据和执行安全 | P0/第 6～7 周 | 将威胁转成越权、注入、泄露、危险副作用和供应链测试 |

仓库目录编号不连续并不代表你漏学；README 中部分“部署可扩展 Agent”“本地 Agent”等章节仍标为 Coming Soon，应以当前仓库状态为准。

## 学习一章时写这张设计卡

```markdown
### 模式名称
- 解决的问题：
- 输入与输出：
- 模型负责：
- 确定性代码负责：
- 允许工具：
- 状态字段：
- 停止条件：
- 失败/越权场景：
- 验证指标：
- 在指标 Agent 中是否采用：采用 / 实验 / 不采用，原因：
```

## 不要求全部运行微软代码

分三层完成：

1. **P0 概念**：中文 README + 英文关键段，画图并完成设计卡。
2. **框架无关实验**：用 fake model/Python 或 LangGraph 实现一个最小模式。
3. **微软框架代码（选做）**：只有你愿意配置 Foundry/Azure，或目标岗位需要时运行。

这样可以避免把时间耗在账号、云资源和特定框架配置上，同时保留课程的设计价值。

## 4 个必须做的实验

1. Tool Use：未知工具、参数错、越权、timeout、重复调用。
2. Planning：静态三步图与模型动态计划比较成功率、步骤和成本。
3. Multi-Agent：单 Agent 与生成/审核双 Agent 比较；保留确定性 Guard。
4. Trust/Security：把文档注入、工具越权和敏感结果泄露加入 golden set。

最终能回答：为什么这个任务需要 Agent？哪些步骤不该由模型决定？如何验证成功？失败后怎样停止、恢复和审计？
