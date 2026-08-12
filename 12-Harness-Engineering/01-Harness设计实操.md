# 用故障场景设计 Agent Harness

配套可运行工程见 [harness-practice](./harness-practice/README.md)。建议先运行 demo，再对照本页逐项阅读运行时和故障测试。

## 1. 从任务契约开始

```python
class TaskSpec(BaseModel):
    task_id: str
    objective: str
    context: str = ""
    expected_metric: str | None = None
    allowed_tools: frozenset[str]
    max_steps: int = 6
    max_cost_units: int = 20
    max_context_chars: int = 8_000
    deadline_seconds: float = 30
    planner_timeout_seconds: float = 10
    cancel_check_timeout_seconds: float = 1
    approval_timeout_seconds: float = 30
    verifier_timeout_seconds: float = 10
```

没有完成条件、预算和允许动作，Agent 就无法可靠判断何时停止。`expected_metric` 是给确定性 Verifier 的显式验收目标，Verifier 不应从自然语言里猜。`max_context_chars` 也不能只检查用户最初的一句话：工程会在每轮调用前重新计算 Task、工具 schema 和累计 observation 的完整负载，避免工具结果逐轮挤爆上下文。

## 2. Tool Registry 元数据

除了 schema 和函数，登记：版本、权限、租户参数、是否有副作用、幂等策略、timeout、每次尝试的成本、输出大小/敏感级别、回滚/补偿能力。Planner 只能看到当前任务允许的工具子集；运行时还必须再次校验，不能把“模型没看见”当成安全边界。

配套工程中的 `query_metric` 把 `tenant_argument="tenant"` 登记在 Tool Registry。即使 Planner 生成 `tenant-b`，Harness 也会用登录用户的 `tenant-a` 做强制比对。

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

副作用工具还有一个额外原则：超时并不代表远端没有执行成功。没有幂等键时，Harness 宁可返回 `UNSAFE_RETRY_BLOCKED`，也不能自动再写一次；有幂等键时也不能仅凭“缓存里还没结果”就重试，因为原线程仍可能运行。

配套工程使用原子幂等状态机演示这一点：开始调用前先占用 `in_progress`，正常返回后写成 `completed`，异常则封存为 `unknown`。线程超时后，紧接着的相同请求会看到“执行中”而被拒绝；晚到结果会在线程内部落表，之后只重放结果。生产环境必须把这份状态放进带唯一约束、租约和 TTL 的持久化存储，并提供对账/补偿流程。

## 4. Verifier 层次

从强到弱：确定性规则/测试 → 独立数据源交叉验证 → 专用 verifier 模型 + rubric → 人工。让同一个模型重读自己的答案可以作为信号，但不是可靠独立验证。Verifier 本身也属于运行时依赖，因此要有独立超时、结构契约，并受任务总 deadline 约束。

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

关闭模型、数据库或 MCP Server 任意一个组件，系统都应在限定时间内进入可解释的失败/降级状态。教学工程证明单进程内不会因自动重试而重复副作用；要承诺“进程崩溃恢复后仍不重复且审计不丢失”，还必须把幂等状态、checkpoint 和 trace 持久化。
