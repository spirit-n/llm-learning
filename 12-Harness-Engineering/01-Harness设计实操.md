# 用故障场景设计 Agent Harness

## 1. 从任务契约开始

```python
class TaskSpec(BaseModel):
    task_id: str
    objective: str
    allowed_tools: list[str]
    max_steps: int = 8
    max_cost_usd: float
    deadline_seconds: int
    requires_approval: bool = False
```

没有完成条件、预算和允许动作，Agent 就无法可靠判断何时停止。

## 2. Tool Registry 元数据

除了 schema 和函数，登记：版本、权限、是否有副作用、幂等策略、timeout、成本等级、输出敏感级别、回滚/补偿能力。Planner 只能从当前任务允许的工具子集中选择。

## 3. 错误分类决定恢复

| 错误 | 例子 | 默认动作 |
|---|---|---|
| validation | 参数/schema 错 | 反馈简化错误，有限修复 |
| permission | 越权表 | 立即拒绝，不重试 |
| transient | 429、短暂网络错误 | 退避重试，受预算限制 |
| task | 证据不足、需求含糊 | 澄清或拒答 |
| permanent | 工具不存在、配置缺失 | 降级/人工，不循环 |
| safety | 注入、危险操作 | 停止并审计 |

“所有异常重试三次”是错误设计。

## 4. Verifier 层次

从强到弱：确定性规则/测试 → 独立数据源交叉验证 → 专用 verifier 模型 + rubric → 人工。让同一个模型重读自己的答案可以作为信号，但不是可靠独立验证。

NL2SQL 可用 parser、EXPLAIN、只读沙箱、结果约束、golden execution result 验证。

## 4.1 可信 Agent 不只是更强的 Prompt

[微软 Trustworthy Agents](https://github.com/microsoft/ai-agents-for-beginners/tree/main/06-building-trustworthy-agents) 和 [Anthropic Trustworthy Agents](https://www.anthropic.com/research/trustworthy-agents) 都强调模型之外的控制。把可信要求落到可执行设计：

| 目标 | Harness 机制 | 本项目证据 |
|---|---|---|
| 人保持控制 | 工具 allow/ask/block、HITL、取消、预算 | 高风险 SQL 必须确认；用户可取消 |
| 最小权限 | 任务级工具子集、只读账户、租户过滤 | 越权 golden set 全部被拒绝 |
| 透明 | trace、引用、SQL/数据来源、状态 | 一次失败可定位到具体节点 |
| 隐私 | 数据最小化、脱敏、保留/删除策略 | trace 无密钥/无不必要 PII |
| 安全恢复 | 错误分类、幂等、checkpoint、有限重试 | 故障注入后状态可解释且不重复副作用 |

系统 Prompt 是其中一层，不能替代数据库权限、执行沙箱和审计。

## 5. 状态机

每个状态写允许进入/离开的事件，例如：`PENDING → RUNNING → WAITING_APPROVAL → RUNNING → SUCCEEDED/FAILED/CANCELLED`。取消和超时是正式状态，不是异常日志。

## 6. 故障注入清单

- 模型 429/超时/返回非法 schema。
- Retriever 空结果/错误版本/越权候选。
- 工具断连/超时/部分执行。
- checkpoint 写入失败。
- 审批超时或拒绝。
- trace 服务不可用。
- token/成本/步骤预算耗尽。

为每个故障写期望状态、是否重试、用户可见消息、审计记录和恢复点。

## 7. 验收

关闭模型、数据库或 MCP Server 任意一个组件，系统都应在限定时间内进入可解释的失败/降级状态；恢复后不会重复副作用，也不会丢失任务审计链。
