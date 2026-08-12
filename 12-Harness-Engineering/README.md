# 12｜Harness Engineering

**安排：** 第 6 周后半，P0/P1。这不是某个框架，而是把模型变成可靠系统的运行时工程。

详细学习：[用故障场景设计 Agent Harness](./01-Harness设计实操.md)。

配套工程：[harness-practice](./harness-practice/README.md)。它用默认离线、可故障注入的 Planner 和工具实现 TaskSpec、完整上下文预算、allowlist、权限与租户隔离、覆盖审批/工具/Verifier 的总 deadline、取消、审批契约、幂等状态机、按尝试计费、timeout/有限重试、输出限流、确定性 Verifier 与脱敏 Trace，并提供真实模型 Planner 的显式 live 测试。

快速开始：

```powershell
cd 12-Harness-Engineering/harness-practice
python -m pip install -e ".[dev,live]"
python -m harness_lab.demo
python -m pytest -q
```

补充教材：微软 AI Agents 课程中的 Trustworthy、Production、Security 章节见 [中文导读](../06-LangGraph/02-微软AI-Agents教程导读.md)。

## 零基础前置

先学完 Tool Calling、LangGraph、Context 和 MCP 的基本流程。把 Harness 想成“驾校教练车的刹车、仪表、规则和安全员”：模型像驾驶员，但系统不能只相信驾驶员每次都做对。

## 组成

```text
Task Spec
  ↓
Context Builder ── Permission/Policy
  ↓
Planner / Router
  ↓
Tool Registry → Guard → Executor
  ↓                    ↓
State/Memory ← Observation/Trace
  ↓
Verifier → Retry/Recovery → Human Review → Result
```

- Task Spec：完成条件（如 `expected_metric`）、预算、截止时间、允许动作。
- Context Builder：按需收集并裁剪上下文。
- Tool Registry：schema、版本、权限、成本和副作用元数据。
- Guard/Executor：校验、沙箱、超时、幂等和审计。
- Verifier：用规则、测试、独立证据或人工验证结果。
- State/Memory：任务状态和长期记忆分开管理。
- Trace：完整记录决策输入、调用、输出与状态迁移。
- Recovery：按错误类型重试、换方案、降级、暂停或人工接管。

## 设计原则

- LLM 负责模糊判断，代码负责确定性约束。
- 重试必须有错误分类、预算和停止条件。
- Verifier 不能只让同一个模型“再看一遍”就算验证。
- 有副作用的工具要求幂等键、dry-run、审批和补偿策略。
- 把上下文、工具、模型、prompt 和 eval 数据都版本化。

## 项目验收

用指标查询 Agent 演练：模型/审批/Verifier 超时或错误协议、跨租户参数、权限拒绝、结果为空/缺字段/异常、工具断连、累计上下文/成本/输出超限、用户取消、人工拒绝，以及副作用执行中、结果未知、完成重放和幂等冲突。每种故障都应有可预测状态、trace 和最终退出路径。

## 面试定义

> Agent = Model + Harness。Harness Engineering 设计模型外的任务规范、上下文、工具、权限、执行、状态、验证、观测、恢复与人工控制，使 Agent 可控、可验证、可恢复和可审计。

## 配套教程怎么用

| 优先级 | 教程 | 它补充什么 | 怎么学 |
|---|---|---|---|
| P0 | [Anthropic：Building Effective Agents](https://www.anthropic.com/engineering/building-effective-agents) | workflow 与 Agent 的区别、简单可组合编排模式 | 给自己的任务做“固定 workflow 还是自治 Agent”选型，并写理由 |
| P0 | [Anthropic：Trustworthy Agents](https://www.anthropic.com/research/trustworthy-agents) | Model、Harness、Tools、Environment 四层与人类控制/隐私/安全 | 转成 allow/ask/block、最小权限、HITL、透明和隐私测试 |
| P2 | [Hugging Face Context Course：Nano Harness](https://huggingface.co/learn/context-course/unit0/introduction) | 从 Skills/MCP/Hooks 走到最小 Agent Harness | 完成本章设计后选做 Unit 6，不用先学全部插件内容 |
