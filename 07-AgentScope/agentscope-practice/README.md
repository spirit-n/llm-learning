# AgentScope 多 Agent 协作与失败边界练习

## 2026-10：版本与能力边界

本工程继续锁定已验证的 `agentscope==2.0.4.post1`，不等于最新版本。官方入口已更新为 [docs.agentscope.io](https://docs.agentscope.io/)，核对时首页为 2.0.9；1.x 示例不可直接混用。2.x 能力图包括工具中间件、context 管理、隔离与服务化，但**本工程只验证下文列出的协作路径**，并未把全部能力接入。先运行现有离线测试，再另建隔离环境按 release notes 做迁移；不要对当前学习环境直接 `pip install -U agentscope`。

这个项目使用 AgentScope 2.0.4 的真实 `Msg`、`Agent`、`ChatModelBase`、`FunctionTool` 和 `Toolkit` API。它不再只演示“按关键字二选一”，而是实现一条完整协作链：Coordinator 将请求交给领域专家，专家通过工具或知识生成草稿，再由无业务工具权限的 Review Agent 审核后交付。

默认 demo 和单元测试使用 `OfflineChatModel`，因此不需要 API Key、不会产生费用；只有显式运行 `tests_live/` 才调用统一配置的真实模型。

## 架构与消息流

```text
UserMsg
  → Coordinator（校验、路由、超时和消息预算）
      ├─ metric_agent → 只读指标工具
      └─ knowledge_agent → 框架知识
  → review_agent（没有业务工具，只审核最小 handoff）
  → completed / rejected / failed
```

`workflow.py` 刻意把协作写成显式的两阶段流程。框架负责 Agent 和 Message 抽象；超时、错误映射、输出长度、最大 handoff 次数等可靠性边界仍由业务 Harness 负责。

默认 Coordinator 每个请求创建一组新的 Agent，避免 Agent memory 在不同请求或用户间串线。如果业务需要连续会话，应按可信 session ID 建立隔离的 Agent/Memory，并配置过期与删除策略，不能把一个全局 Agent 实例共享给所有用户。

## 运行

```powershell
cd 07-AgentScope/agentscope-practice
python -m pip install -e ".[dev]"
python -m as_lab.demo
python -m pytest -q
```

首次安装 AgentScope 的依赖较多，等待时间会明显长于前三个工程。

## 建议阅读顺序

1. `src/as_lab/domain.py`：稳定的协作结果与可观测消息模型。
2. `src/as_lab/tools.py`：普通函数如何适配成 AgentScope Tool，并添加只读权限策略。
3. `src/as_lab/model.py`：离线模型如何产生 `ToolCallBlock`、读取工具结果和执行审核协议。
4. `src/as_lab/agents.py`：两个专家和一个无业务工具权限的审核 Agent 如何组装。
5. `src/as_lab/routing.py`：什么时候应使用确定性 Router，而不是再花一次模型调用。
6. `src/as_lab/workflow.py`：跨 Agent 消息、最小 handoff、超时、拒绝和失败隔离的主体。
7. `src/as_lab/demo.py`：观察工具 schema、目标专家、审核结果和消息流。
8. `tests/test_multi_agent_workflow.py`：逐个运行超时、异常、审核拒绝、协议错误与日志脱敏场景。
9. `COMPARISON.md`：和上一章 LangGraph 做对照。

## 失败边界

| 场景 | Coordinator 行为 | 为什么不继续对话 |
|---|---|---|
| 输入为空或过长 | `INVALID_REQUEST`，不调用 Agent | 防止无效成本和超大上下文 |
| 专家超时/异常 | `SPECIALIST_TIMEOUT/FAILED` | 防止单个 provider 拖垮请求 |
| Agent 返回 `None`、dict、普通字符串或空 Msg | `INVALID_AGENT_RESPONSE` | 运行时验证 Msg 类型与可取文本，异常不击穿 Coordinator |
| 合法 Msg 的草稿过长 | `INVALID_DRAFT` | Agent 文本不能直接当可信结果 |
| 审核明确拒绝 | `rejected` | 不让错误工具结果进入最终答案 |
| 审核格式不合法 | `REVIEW_PROTOCOL_ERROR` | 自然语言“看起来没问题”不是机器可执行协议 |

每次运行最多一次专家 handoff 和一次审核 handoff。只有在工具具备幂等语义时，才应考虑由外层 Harness 增加重试。

## 版本提醒

当前 2.0.4 API 统一使用 `agentscope.agent.Agent`，通过 `ReActConfig` 配置推理—行动循环。旧教程中的 `ReActAgent`、`AgentBase` 或 `Toolkit.register_tool_function` 导入/调用方式不要直接照抄；以项目锁定版本和当前官方文档为准。

本例把路由写成普通确定性函数，因为“关键字分类”不需要再调用一次模型。多 Agent 不是目标本身，只有上下文隔离或专业分工确实带来收益时才值得增加角色。

## 推荐实验

1. 把 `reply_timeout_seconds` 调到 `0.001`，观察超时是否被限制在当前请求。
2. 在 Stub Agent 中返回空文本、超长文本和错误审核前缀，逐个运行对应测试。
3. 给 Review Agent 临时添加指标工具，再思考为什么审核阶段的权限扩大了攻击面。
4. 用 20 条固定问题比较“仅专家”和“专家 + 审核”的正确率、模型调用数、延迟和失败定位成本。

## 真实模型实验

`tests_live/test_live_agentscope_agent.py` 使用 AgentScope 的 `OpenAIChatModel`、`Agent` 与 `Toolkit` 跑完整 ReAct 工具循环。endpoint、model 和密钥均来自 [统一 live 配置](../../shared/README.md)，运行 `python -m pytest -q tests_live -m live`。
