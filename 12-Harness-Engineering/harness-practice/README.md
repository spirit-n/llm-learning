# Agent Harness 故障与恢复练习

这个工程把模型外的可靠性机制写成一个小型、可单测的运行时。它不假设模型会“自觉守规矩”，而是在模型调用前后设置强制边界：

```text
TaskSpec → 完整 Planner payload/context/deadline/cancel → Planner contract
→ allowlist/schema/permission/tenant scope → approval timeout/幂等状态机
→ timeout/retry/attempt cost/output limit → Observation
→ Verifier contract/timeout → Result + redacted Trace
```

默认使用 `ScriptedPlanner` 和固定工具，不调用模型。显式运行 `tests_live/` 时，才让环境变量配置的真实模型担任 Planner；权限、预算、执行和验证仍由同一个 Harness 控制。

## 运行

```powershell
cd 12-Harness-Engineering/harness-practice
python -m pip install -e ".[dev,live]"
python -m harness_lab.demo
python -m pytest -q
```

真实模型验证使用 [统一配置](../../shared/README.md)：

```powershell
python -m pytest -q tests_live -m live
```

## 阅读顺序

1. `src/harness_lab/models.py`：TaskSpec、状态、Observation、Trace 和最终结果契约。
2. `src/harness_lab/runtime.py`：总 deadline、取消、预算、Planner 契约、工具执行和所有稳定退出路径。
3. `src/harness_lab/registry.py`：工具 schema、版本、风险、租户字段、成本、副作用和输出上限。
4. `src/harness_lab/idempotency.py`：为什么跨运行副作用去重必须落在模型之外。
5. `src/harness_lab/tools.py`：固定数据、租户参数与瞬时故障注入。
6. `src/harness_lab/verifiers.py`：为什么结果验证不能只靠模型自审。
7. `src/harness_lab/trace.py`：字段和值两层脱敏、长文本截断和 UTC 时间戳。
8. `tests/test_harness.py`：逐个运行 36 条成功、安全、恢复与失败路径。
9. `tests_live/test_live_harness.py`：真实模型只替换 Planner，Harness 边界不变。

## 已覆盖的故障

| 故障 | Harness 行为 |
|---|---|
| 上下文超限 | 每轮按任务、工具 schema、已有 observation 的真实 Planner 负载重新计算并拒绝 |
| 任务总 deadline / 用户取消 | 覆盖 Planner、审批、工具和 Verifier，在控制点稳定退出并保留已有 observation |
| 模型超时 | 有预算地重试，耗尽后稳定失败 |
| 模型返回错误结构 | Pydantic 契约校验后返回 `PLANNER_CONTRACT_INVALID` |
| Planner 篡改 Task/Observation 或用 `model_construct` 绕过校验 | 运行时深快照、传参深拷贝并强制二次校验 |
| 取消源卡住、抛异常、返回非 bool / Verifier 期间收到取消 | 返回稳定失败或取消状态，不让异常击穿、也不误报成功 |
| 工具不在 allowlist / 权限不足 | 立即拒绝，不重试 |
| Planner 请求其他租户 | Harness 比对登录租户，返回 `TENANT_SCOPE_VIOLATION` |
| 参数 schema 错误 | handler 执行前拒绝 |
| 工具瞬时断连 | 按错误类型有限重试，每次真实尝试都计入成本 |
| 重复调用 | 停止循环 |
| 步数/成本耗尽 | 进入明确失败状态 |
| 审批卡住或返回错误类型 | 独立 timeout 和契约校验，handler 不会执行 |
| 有副作用工具 | 等待审批；handler 一旦启动，超时或异常都不自动重试 |
| 相同幂等键重复提交 | 原子维护 `in_progress/completed/unknown`；并发拒绝、晚到结果可重放、参数变化报告冲突 |
| 工具输出过大 | 在送回上下文前拒绝，防止上下文洪泛 |
| 空结果、错指标、缺字段、非有限数、异常值、多行只回答一部分 | Verifier 按 TaskSpec 的显式验收目标拒绝 |
| Verifier 卡住或返回错误结构 | 独立 timeout 和 Pydantic 契约校验后稳定失败 |
| Trace 含 key 或长文本 | key 脱敏、长内容截断 |

## 建议实验

1. 先运行全部测试，再用 `-k tenant`、`-k idempotency`、`-k deadline` 分别观察安全、恢复和停止条件。
2. 把 `DemoTools(transient_failures=1)` 改成 2，比较 `max_cost_units` 是否足够覆盖每次真实尝试。
3. 在 live Planner 的系统提示中故意要求查询 `tenant-b`，确认模型即使照做也会被 Harness 拒绝。
4. 运行 `-k idempotent_side_effect_timeout`，观察第一次返回“结果未知”、紧接着的请求显示“执行中”、晚到结果落表后第三次只重放而不重写。

线程 timeout 不能强制终止已经开始的 Python 函数，因此审批与 Verifier 回调必须保持无副作用。教学版内存幂等表能说明状态机和并发占用，但进程崩溃后会丢失；生产环境还需要数据库 statement timeout、可取消的异步 I/O、进程隔离、持久化 checkpoint，以及带唯一约束、租约、TTL、对账与补偿的幂等设施。
