# AgentScope 与 LangGraph 对照

| 维度 | 本章 AgentScope | 上一章 LangGraph |
|---|---|---|
| 抽象中心 | Agent、消息、模型和工具协作 | State、Node、Edge 和 checkpoint |
| 工具循环 | `Agent` 内部 ReAct 循环；外层 Coordinator 限制两次 handoff | 节点和条件边显式表达 |
| 路由 | 确定性函数选择专家，消息交接由 Coordinator 记录 | conditional edge，可视路径更清楚 |
| 恢复 | 需进一步使用 AgentScope state/session 能力 | checkpointer + thread ID + interrupt/resume 是图的一等能力 |
| 适合场景 | 角色协作、消息驱动、多 Agent 实验 | 强控制、长流程、人工审批、可恢复任务 |

本练习的指标问答非常简单，单 Agent 就能完成。加入 Review Agent 的主要价值是演示上下文隔离、最小权限和失败拦截，不代表答案一定更好；是否值得增加它必须用评测数据回答。SQL Guard、权限和副作用幂等仍应由确定性代码负责。
