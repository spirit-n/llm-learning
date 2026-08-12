# 自定义 HTTP、A2A 与 MCP

| 维度 | 自定义 HTTP | A2A | MCP |
|---|---|---|---|
| 主要对象 | 自己约定 | Agent Card、Message、Task、Artifact | Tool、Resource、Prompt |
| 对方 | 任意业务服务 | 独立且内部可不透明的 Agent | 工具/资源服务 |
| 长任务状态 | 自己设计状态、合法迁移、查询和事件游标 | 协议定义通用 Task 状态与更新事件 | 不是核心抽象 |
| 能力发现 | 私有 `/agents` | Agent Card | tools/resources/prompts 列表 |
| 结果 | 自己约定 `artifact` 字段和下载方式 | Artifact/Part | Tool result 或 Resource 内容 |
| 幂等 | 自己定义 header、冲突和重放语义 | 仍需业务层实现，A2A 不替你做业务去重 | 工具调用也需业务层实现 |
| 错误 | 自己约定 HTTP 状态码和错误 JSON | 协议错误 + Task 的 failed/rejected/canceled | 协议错误 + Tool result/error |
| 适合本例 | 能跑，但跨团队约定多 | 报告 Agent 跨服务委托 | 数据 Agent 访问数据库工具 |

组合方式：数据 Agent 先通过 MCP 查询受控数据，再通过 A2A 把最小化后的统计摘要委托给报告 Agent。不要把原始敏感行交给远端 Agent。

注意 A2A 标准化的是跨 Agent 交互语义，不会自动提供数据库事务、幂等唯一约束、租户授权或 Artifact 存储。本项目的 `execution.py` 就是协议之外仍必须存在的业务层。
