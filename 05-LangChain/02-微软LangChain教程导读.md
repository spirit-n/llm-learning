# Microsoft LangChain for Beginners 中文学习路线

主仓库：[microsoft/langchain-for-beginners](https://github.com/microsoft/langchain-for-beginners)。当前课程包含 setup + 8 个正式章节，使用 Python，前置要求包括基本 Python、`async/await`、pip，以及 LLM/Prompt/token 基础。

## 先做哪个环境选择

课程提供 GitHub Codespaces 和本地开发。你已经在学习 Anaconda/VS Code，因此推荐本地独立 conda 环境，不要再同时学 Codespaces：

```powershell
conda create -n ms-langchain-course python=3.11 -y
conda activate ms-langchain-course
git clone https://github.com/microsoft/langchain-for-beginners.git
cd langchain-for-beginners
python -m pip install -r requirements.txt
```

课程 README 当前要求 Python 3.10+；示例选 3.11 是为了学习兼容性。执行前仍应查看 [Course Setup](https://github.com/microsoft/langchain-for-beginners/tree/main/00-course-setup) 的最新要求。

课程默认可使用 GitHub Models 或 Microsoft Foundry。不要把 token 写进 Python 代码、Notebook 或 Git；使用 `.env`，并确认 `.gitignore` 排除它。学习 token 的申请与权限时，以 GitHub 当前界面和仓库 setup 为准。

## 章节逐一怎么学

| 章节 | 讲什么 | 本计划优先级/周次 | 你要完成什么 |
|---|---|---|---|
| [00 Course Setup](https://github.com/microsoft/langchain-for-beginners/tree/main/00-course-setup) | Python、环境、模型访问、`.env`、测试连接 | P0/第 1 周 | 独立环境安装成功；运行 setup test；能解释 API key 为什么不能进 Git |
| [01 Introduction](https://github.com/microsoft/langchain-for-beginners/tree/main/01-introduction) | LangChain 定位、Model、Message、第一次 LLM 调用 | P0/第 1 周 | 画出用户→LangChain Model→Provider→响应；修改 system/user message |
| [02 Chat Models](https://github.com/microsoft/langchain-for-beginners/tree/main/02-chat-models) | 消息、对话、streaming、temperature、错误处理 | P0/第 1 周 | 比较 invoke/stream；测试 timeout/错误；记录 token 与耗时 |
| [03 Prompts, Messages, Outputs](https://github.com/microsoft/langchain-for-beginners/tree/main/03-prompts-messages-outputs) | Prompt template、消息数组、结构化输出、Pydantic | P0/第 1 周 | 把自由文本分类改为 Pydantic schema；准备 20 条格式测试 |
| [04 Function Calling & Tools](https://github.com/microsoft/langchain-for-beginners/tree/main/04-function-calling-tools) | Tool schema、绑定、参数、类型安全 | P0/第 1/4 周 | 做指标定义 Tool；测试缺参数、错类型、未知工具；与手写 loop 对照 |
| [05 Agents](https://github.com/microsoft/langchain-for-beginners/tree/main/05-agents) | ReAct/Agent loop、`create_agent`、middleware | P0/第 4 周 | 限制最大步骤；工具权限；比较 Agent 与确定性 workflow |
| [06 MCP](https://github.com/microsoft/langchain-for-beginners/tree/main/06-mcp) | MCP Server、stdio、工具集成、多 Server | P1/第 6 周 | 先理解 LangChain 如何消费 MCP Tool；Server 深入用微软 MCP 独立课程 |
| [07 Documents, Embeddings, Semantic Search](https://github.com/microsoft/langchain-for-beginners/tree/main/07-documents-embeddings-semantic-search) | 文档加载、chunk、embedding、相似度检索 | P0/第 2 周 | 跑通 10 篇文档 dense baseline；保留 chunk ID/metadata；不要止步 Demo |
| [08 Agentic RAG](https://github.com/microsoft/langchain-for-beginners/tree/main/08-agentic-rag-systems) | Agent 决定何时检索、retrieval tool、智能问答 | P1/第 5 周 | 与固定 RAG 对照：成功率、调用次数、延迟、错误路径，而非默认 Agentic 更好 |

## 每章的正确学习顺序

1. README 中的类比和 Learning Objectives。
2. 跑最小 `code` 示例。
3. 逐行打印输入/输出对象，确认不是“看起来能跑”。
4. 做 assignment，不先开 solution。
5. 把场景替换成你的指标查询或企业文档。
6. 对照当前 [LangChain 官方文档](https://docs.langchain.com/oss/python/langchain/overview) 检查 API。

## 这套课没有替你解决什么

- 工具权限、SQL AST、数据库只读账户。
- RAG 的 hybrid/BM25/RRF/reranker 与系统评测深度。
- LangGraph checkpoint、恢复和显式状态机。
- 生产的限流、成本、审计和故障注入。

这些仍按本仓库对应章节学习。入门课程的“运行成功”只是起点。

## 最终验收作业

将课程中的通用 Agent 改成指标查询 Agent：

```text
用户问题 → 指标定义 Tool → schema Tool → 只读 SQL Tool → 答案
```

要求 fake model 测试、Pydantic 参数、最大 6 步、权限拒绝、超时、重复调用检测、结构化 trace。能解释不用 LangChain 如何手写，以及框架替你做了什么。
