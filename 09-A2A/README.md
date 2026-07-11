# 09｜Agent2Agent（A2A）

**安排：** 第 6 周 1～2 小时，P2。主线只要求形成概念卡；编码实验降为 P3。

详细学习：[A2A 概念、最小实验与 MCP 对比](./01-A2A最小实验.md)。

## 零基础前置

必须先能讲清 Client/Server、HTTP、Agent 与 MCP。A2A 是 P2，不理解网络协议细节也可以先学概念；只需画清楚两个独立 Agent 谁调用谁、任务状态由谁保存。

## 定位

- MCP 主要连接 Agent 与工具/资源。
- A2A 连接独立、可能内部不透明的 Agent 系统，使其发现能力、交换消息并协作完成任务。
- 多 Agent 框架内的函数调用不等于跨系统 A2A 协议。

## 了解内容

- Agent 能力发现与 Agent Card。
- message、part/artifact、task 与生命周期。
- 同步、流式、异步/长任务的交互思想。
- 身份、授权、租户隔离、数据边界和跨 Agent trace 关联。

## 可选最小实验（P3）

让“数据分析 Agent”把报告生成委托给另一个独立 Agent 服务。先用普通 HTTP 自定义接口实现，再对照 A2A 描述它减少了哪些私有约定、增加了哪些协议复杂度。

## 面试回答

> 企业早期更常见的需求是把数据库、文档、工单等工具安全接入 Agent，因此优先落地 MCP。只有多个自治 Agent 跨团队、框架或服务边界协作时，A2A 才体现更明显价值。

## 资料怎么用

| 优先级 | 资料 | 它是干什么的 | 零基础怎么使用 |
|---|---|---|---|
| P2 | [A2A GitHub](https://github.com/a2aproject/A2A) | A2A 项目总入口，提供定位、快速开始、SDK/示例、版本和 release | 先读 README，重点回答“它解决谁和谁通信”。只做一个最小委托任务，不需要深入所有语言 SDK |
| 查规则/P3 | [A2A Specification](https://github.com/a2aproject/A2A/blob/main/docs/specification.md) | 正式定义 Agent Card、Message、Task、Artifact、状态和协议绑定 | 先看 Introduction 和核心对象，其他章节按最小实验需要查询。协议仍在演进，写代码前核对 release 版本 |

这一章的合格标准是能在 3 分钟内解释 MCP 与 A2A 的边界，并画出 Agent Card、Message、Task、Artifact 的关系。没有完成 RAG、工具调用和 MCP 前，不做编码实验。
