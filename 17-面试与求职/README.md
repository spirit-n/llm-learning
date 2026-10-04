# 17｜面试与求职

## 2026-10：新增工程追问

1. Chat Completions 与 Responses 为什么不只是换 URL？工具结果如何对应调用，继续对话要保留哪些输出项？
2. SQLite checkpoint 为什么不自动保证外部退款 exactly-once？进程崩溃留下 unknown 如何处理？
3. 多工具轨迹为什么要评必要先后关系，而不是唯一固定序列？合法重试与重复副作用如何区分？
4. 引用 ID 合法为什么不等于答案被证据支持？压缩率高为什么不等于任务能恢复？
5. MCP 规范、SDK 与对端 capabilities 分别说明什么？为什么当前项目保留 `<2`？
6. OTel GenAI 字段还在演进，如何版本化映射？为什么 trace 不应直接保存 Prompt/密钥？

每题用一个仓库测试说明答案，并明确离线模拟与真实验证的边界；不会的内容先补实验，不把“了解过名字”写成生产经验。

## 零基础提示

面试不要求用术语堆满答案。优先用自己的项目数据流解释，再补术语。确实没做过的内容明确说“了解原理但未做生产实践”，然后说明你会怎样验证，不要编造经验。

## 目标岗位

- AI 应用工程师 / LLM Application Engineer
- Agent 工程师 / 智能体平台后端
- RAG / 知识库工程师
- LLM 后端工程师
- AI Platform Engineer

你的定位不是“从零转算法”，而是：**懂 Java/后端与数据系统，能用 Python 把 RAG、Agent、MCP 接入真实业务，并用评测、安全和观测保证可靠性。**

## 8～10 周求职节奏

- 第 1 周：收集 30 个 JD，建立技能频次和岗位画像。
- 第 2～3 周：优化个人介绍，写项目一简历草稿，联系同行了解面试流程。
- 第 4 周：开始投递 10～15 个校准岗位。
- 第 5～6 周：每周 15～25 个高匹配投递；模拟面试并按反馈补缺。
- 第 7～8 周：集中投递、内推、复试准备；每天复盘漏斗。

如果改为 10 周版：

- 第 1～4 周：打基础并完成 RAG 项目，先积累可写进简历的指标。
- 第 5～6 周：完成 Agent 项目并开始小批量投递，用反馈校准简历。
- 第 7～8 周：补 MCP、评测、部署、安全和可观测性，形成工程化差异。
- 第 9～10 周：作品集、演示视频、系统设计和模拟面试冲刺。

如果目标是 2026 年金九银十：从 2026-07-13 开始执行 10 周版，2026-09-07 前进入集中投递，2026-09-20 前完成作品集冲刺，2026-09-21 到 2026-10-31 按面试反馈滚动补缺。

## 投递表字段

```text
公司 | 岗位 | 来源 | 日期 | 匹配度 | JD关键词
简历版本 | 当前阶段 | 下次动作 | 面试问题 | 失败原因 | 复盘
```

关注漏斗：投递 → 简历回复 → 一面 → 二面 → offer。回复低优先检查岗位匹配与简历；面试通过低优先检查项目深度、基础和表达。

## 简历项目公式

```text
场景/规模 + 你的职责 + 关键设计 + 可验证结果 + 工程保障
```

示例（数字必须替换为真实实验）：

> 设计企业文档 RAG，构建 BM25+dense 混合召回、RRF 与 reranker 流程；基于 50 条领域 golden set 将 Recall@5 从 X 提升至 Y，同时通过引用、权限过滤和 RAGAS/人工评测定位幻觉，并记录 P95 延迟与单请求成本。

## 高频题目录

### RAG（P0）

- RAG 为什么答错？如何把错误定位到解析、chunk、召回、排序、上下文、生成？
- chunk 大小和 overlap 如何选？为什么需要 parent-child？
- dense 与 BM25 各自擅长什么？RRF 如何融合？
- reranker 放哪一层？怎样判断它值不值得增加延迟？
- 如何做权限、增量更新、引用和评测？

### Agent/LangGraph（P0）

- Agent 与 workflow 区别？为什么 Agent 容易失控？
- 为什么用 LangGraph，而不是 `while True`？
- State/Node/Edge/checkpoint/HITL 各解决什么？
- 如何限制循环、重试和工具副作用？
- 多 Agent 什么时候真的优于单 Agent？

### LangChain/AgentScope（P1）

- 框架给你什么抽象？哪些逻辑不应交给框架/LLM？
- LangChain 与 LangGraph 如何分工？
- AgentScope 与 LangGraph 的抽象和多 Agent 方式有何差异？
- 框架升级快，怎样控制依赖和迁移风险？

### MCP/A2A（P0/P2）

- MCP、Function Calling、REST 的关系？
- tools/resources/prompts 如何选择？stdio 与 HTTP 如何选择？
- MCP Server 如何做认证、权限、审计和输入/输出安全？
- MCP 与 A2A 的边界？为什么先落地 MCP？

### Context/Harness/评测（P0/P1）

- Context Engineering 为什么不是“写长 prompt”？
- 工具返回太长、历史膨胀、schema 太多怎么办？
- 什么是 Harness Engineering？Verifier 如何避免自证？
- 如何建立 Agent golden set？LLM-as-a-Judge 有什么偏差？
- trace 应记录什么，如何兼顾隐私？

### 模型/部署（P1/P2）

- Attention 的 Q/K/V、multi-head、causal mask 是什么？
- RAG、微调、工具调用如何选？LoRA/QLoRA 是什么？
- 如何处理限流、超时、并发、幂等、降级、成本和监控？
- Prompt injection 与工具越权如何防？

## 回答框架

优先用：**定义 → 解决的问题 → 方案/流程 → 取舍 → 项目证据 → 风险**。避免只背名词或只说“用了某框架”。

## 配套复习资料

| 资料 | 用途 | 使用方式 |
|---|---|---|
| [Microsoft AI Agents Study Guide](https://github.com/microsoft/ai-agents-for-beginners/blob/main/STUDY_GUIDE.md) | 复习 Tool、Agentic RAG、规划、多 Agent、协议、Context、记忆、生产和安全 | 第 8 周按面试反馈查缺；不以“看完”代替口述和模拟面试 |
| [章节配套教程索引](../00-学习规划/章节配套教程索引.md) | 按薄弱主题返回权威教程 | 一次只补一个高频缺口，补完立刻做题/项目验证 |
