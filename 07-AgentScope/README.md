# 07｜AgentScope 与多智能体

**安排：** 第 5 周 0.5～1 天，P1。目标是了解一个国内活跃的 Agent 框架并建立框架对比能力；8 周主项目仍以 LangGraph 为主，不维护两套完整实现。

详细学习：[AgentScope 安装、概念与对照实验](./01-AgentScope入门实操.md)。

配套工程：[agentscope-practice](./agentscope-practice/README.md)。它使用当前 AgentScope 2.0.4 的 Message、Agent、Tool、Toolkit 和 ReAct 配置；默认离线演示专家路由、无工具权限的审核 Agent、显式消息流、超时与失败隔离，`tests_live/` 验证真实模型工具循环。

快速开始：

```powershell
cd 07-AgentScope/agentscope-practice
python -m pip install -e ".[dev]"
python -m as_lab.demo
python -m pytest -q
```

框架无关的 Agent 设计模式可结合 [微软 AI Agents 教程导读](../06-LangGraph/02-微软AI-Agents教程导读.md)，再用 AgentScope 完成单/多 Agent 对照。

## 零基础前置

先完成一个单 Agent 工具调用，再学习多 Agent。你需要会 Python 函数、类的基本读法和异步的直觉；暂时不需要分布式系统知识。多 Agent 看不懂时先退回单 Agent，不要靠增加角色解决问题。

> 注意：AgentScope 与历史上的 ModelScope-Agent/ms-agent 不是同一学习入口。本计划以 `agentscope-ai/agentscope` 和 `doc.agentscope.io` 当前文档为准。

## 必学内容（P1）

- 安装、message、model、tool，以及当前统一 `Agent` 中由 `ReActConfig` 控制的推理—行动循环。
- 一个 routing/handoff 示例，并观察消息和工具结果怎样流动。
- 与 LangGraph 比较抽象中心、显式控制流和状态恢复方式。

memory、state/session、concurrent agents、Studio、tracing、evaluation、MCP、Skills 和 A2A 支持均为按 JD 选修，不要求在本周展开。

## 必做最小实验

1. 用 AgentScope 实现“指标分析 Agent”，复用同一工具接口。
2. 增加一个 routing，让两类输入走不同工具或处理路径。
3. 用同一任务与 LangGraph 实现比较代码量、控制流可见性、恢复方式和调试体验。

## 可选对照实验（P2）

把任务拆成 schema agent、SQL agent、review agent，再与单 Agent 比较任务成功率、调用次数、延迟、token 和失败可定位性。这个实验优先用已经掌握的 LangGraph 完成；时间充足时再用 AgentScope 复刻，不因多 Agent API 阻塞主线。

## 与 LangGraph 的比较维度

| 维度 | 要观察什么 |
|---|---|
| 抽象中心 | Agent/消息协作，还是状态图/工作流 |
| 控制流 | routing/handoff 与显式 edge 的表达差异 |
| 持久化恢复 | session/state/checkpoint 如何落地 |
| 多 Agent | 创建容易不等于质量更好，是否真的需要角色拆分 |
| 观测与评测 | 能否定位某一步的上下文、工具和状态问题 |

## 面试结论

框架选型应由任务可控性、持久化恢复、多 Agent 必要性、团队栈和运维约束决定。默认先做单 Agent/显式 workflow；只有角色上下文隔离、并行专长或跨系统自治确有收益时才增加 Agent 数量。

## 资料怎么用

| 优先级 | 资料 | 它是干什么的 | 零基础怎么使用 |
|---|---|---|---|
| P0 | [AgentScope Tutorial](https://doc.agentscope.io/tutorial/) | 官方分步教程，从安装、Message、Model、Tool 到 ReAct Agent | 这是首选入口。按页面顺序做到第一个 ReAct Agent；每完成一步，打印对象和消息，确认数据如何流动 |
| P0 | [AgentScope 文档首页](https://doc.agentscope.io/) | 整个文档目录，包含 workflow、memory、MCP、Skill、A2A、Studio、tracing 和 evaluation | 把它当地图。先看 Tutorial，遇到本周具体功能再从目录进入，不要从头读完所有功能 |
| 查示例/P1 | [AgentScope GitHub](https://github.com/agentscope-ai/agentscope) | 源代码、README、examples、版本发布和 issue；可确认真实安装方式和最新变化 | 先看 README/Quickstart 和与你的实验同名的 example。不要直接复制大型多 Agent 示例；先检查发布时间和当前分支 |
| 原理/P2 | [AgentScope 论文](https://arxiv.org/abs/2402.14034) | 解释框架提出时的设计目标、消息交换、多 Agent 平台架构和实验 | 非科班不要求通读。先看摘要、架构图、结论；数学/实验细节看不懂可跳过，用于回答“它为什么这样设计” |

这一章只需要做到：一个 Agent、一个 Tool、一个 routing 示例和一次 LangGraph/AgentScope 框架对照。单/多 Agent 对照属于 P2，其余功能按岗位需求补。
