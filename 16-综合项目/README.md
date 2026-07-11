# 16｜综合项目与作品集

三个项目不是平行重复：项目一证明检索与评测能力；项目二证明 Agent 工作流与数据工程能力；项目三证明协议、Harness、安全和生产化能力。可以放在同一个 monorepo 中逐步演化。

## 零基础使用方式

不要第一天创建完整 monorepo。第 2 周先建立项目一的最小 `rag_demo.py`；功能稳定后再拆分目录。每增加一个模块都回答：输入是什么、输出是什么、失败怎么办、怎样测试。目录结构是最终目标，不是开始门槛。

## 推荐仓库结构

```text
llm-data-agent/
├── apps/api/                 # FastAPI
├── packages/llm/             # provider adapter
├── packages/rag/             # ingest/retrieve/rerank/context
├── packages/agent/           # LangGraph workflow
├── packages/tools/           # tool contracts and guards
├── packages/mcp_server/      # ClickHouse MCP
├── evals/                    # datasets, runners, reports
├── tests/
├── deploy/                   # Docker/compose/observability
└── docs/                     # architecture, ADR, failure cases
```

## 项目一：企业知识库 RAG（第 2～3 周）

### 用户价值

面向接口文档、指标口径、故障手册等内部资料，提供有权限、有引用、可评测的问答。

### P0 功能

- Markdown/PDF 解析、清洗、版本和 metadata。
- 至少两种 chunk 策略对比。
- dense + BM25/sparse + RRF + reranker。
- tenant/department metadata filter。
- 带来源、标题、页码/chunk ID 的引用；证据不足拒答。
- 30～50 条 golden set 和 baseline 对照报告。

### P1/P2 扩展

- parent-child、query rewrite/HyDE、增量索引与删除一致性。
- 多模态表格/图片解析；选做 GraphRAG 或 Agentic RAG。
- 用户反馈闭环和 hard negative 挖掘。

### 必须展示的数据

| 项 | Baseline | Hybrid | Hybrid + Rerank |
|---|---:|---:|---:|
| Recall@5 | 待测 | 待测 | 待测 |
| MRR | 待测 | 待测 | 待测 |
| Faithfulness | 待测 | 待测 | 待测 |
| P95 延迟 | 待测 | 待测 | 待测 |
| 平均成本 | 待测 | 待测 | 待测 |

不要预填漂亮数字；跑真实实验后再写。

## 项目二：ClickHouse 指标查询 Agent（第 4～5 周）

### 流程

```text
意图分类 → 指标/schema 检索 → SQL 生成 → SQL Guard
→ [人工确认] → 执行 → 结果验证 → 修复/退出 → 解释与引用
```

### P0 功能

- LangGraph 显式状态和受限路径。
- SQL 只读 AST 校验、库表/字段权限、limit、timeout、扫描限制。
- 执行错误分类，最多两次针对性修复；重复 SQL 检测。
- checkpoint、interrupt/resume、trace。
- SQL 显示、指标口径与数据来源，便于审计。
- NL2SQL execution accuracy、tool accuracy、goal success 与安全违规率。

### AgentScope 对照（P1）

用 AgentScope 重建一个小版本，比较单 Agent、多 Agent、LangGraph 三种实现的成功率、步骤、token、延迟、可调试性。结论由数据决定，不预设框架胜负。

## 项目三：ClickHouse MCP + Agent Harness（第 6～7 周）

### P0 功能

- stdio 与 Streamable HTTP MCP Server。
- tools/resources 分层；schema 和指标口径可作为按需资源。
- authentication/authorization、白名单、审计、脱敏、timeout。
- Harness 的 task spec、context builder、tool registry、guard、executor、verifier、recovery 和 HITL。
- Docker 化、健康检查、结构化日志、指标和 trace。
- 故障注入与安全测试报告。

### P2 扩展

- A2A 报告生成 Agent；跨 Agent trace 关联。
- 队列化长任务、模型降级、审批回调。

## 每个项目 README 必须回答

1. 用户问题和非目标是什么？
2. 为什么选择这套架构？替代方案是什么？
3. 数据与权限边界是什么？
4. 关键失败模式如何发现、处理和恢复？
5. 用什么数据集和指标证明改进？
6. 如何本地运行、测试、部署和复现？
7. 当前限制与下一步是什么？

## 演示视频脚本（3～5 分钟）

- 30 秒：问题与目标。
- 45 秒：架构和关键取舍。
- 90 秒：成功流程。
- 45 秒：故意触发失败/越权，展示 guard、trace、恢复。
- 45 秒：评测数据与优化前后。
- 30 秒：限制与下一步。

## 额外项目教程（完成三个主项目后再看）

| 教程 | 用途 | 取舍 |
|---|---|---|
| [Hugging Face Agents Course / Final Project](https://github.com/huggingface/agents-course) | 提供 Agent 课程最终作业和自动评测/benchmark 思路 | 可做额外认证/对照，不替代具有业务差异化的 RAG、指标 Agent、MCP 项目 |
| [Made With ML](https://madewithml.com/courses/mlops/) | 帮助把作品从 Notebook 变成有测试、服务、监控和版本的工程 | 只选对当前作品有直接帮助的章节 |
