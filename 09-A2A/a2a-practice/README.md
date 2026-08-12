# A2A 委托与任务生命周期练习

同一个“数据 Agent 委托报告 Agent”的场景实现两遍：

- `custom_http.py`：自己约定发现、幂等、任务、事件游标、状态、取消和错误字段。
- `a2a_server.py`：使用官方 `a2a-sdk` 1.x 的 Agent Card、Message、Task、Artifact、AgentExecutor 和 HTTP+JSON/REST 路由。

两种协议入口都把任务状态与业务执行放在独立领域层中。默认实现使用内存存储，便于离线、确定性地观察状态机；生产环境应替换成有事务唯一键的数据库和可重放事件系统。

## 架构与生命周期

```text
Caller / Data Agent
  → 能力发现（私有 /agents 或标准 Agent Card）
  → 委托消息 + trace ID + idempotency key
  → 协议适配层（custom HTTP 或 A2A Executor）
  → 业务执行账本
      submitted → working → completed
                    ├──────→ failed
      submitted ────┬──────→ rejected
                    └──────→ canceled
  → 状态事件 + Artifact
```

终态不可再次迁移。相同租户、相同幂等键、相同输入返回已有任务/Artifact；幂等键相同但输入不同返回冲突，不能静默复用旧报告。

请求正文和 A2A `metadata` 都是不可信输入：`traceId/idempotencyKey` 必须经过类型与长度校验，租户身份只从可信网关头建立；邮箱、手机号、Bearer token、`sk-`/API key 等敏感内容会在执行前拒绝。内存账本只适合单进程教学，不能证明多进程并发下的原子幂等，生产实现必须依赖数据库唯一约束或等价事务机制。

私有 HTTP 的聚合摘要只接受有限的 `int/float`：`bool` 虽然在 Python 中是 `int` 子类，也会被明确拒绝；`NaN`、`Infinity`、`-Infinity` 与数字字符串同样拒绝。领域服务先规范化并按指标名排序，再用同一份规范化表示生成内存快照、HTTP JSON 和 payload digest；记录中的摘要还是只读快照，避免“哈希的是原输入、保存或后来修改的是另一份输入”。

对正在 `working` 的 A2A Task 发起取消时，业务 Execution 与协议 Task 都进入 `canceled`；即便报告生成器稍后返回，也不能补写 Artifact 或变回 `completed`。相同幂等键再次委托会看到已有 `canceled` 终态并被拒绝，而不是偷偷启动第二份工作。`tests/test_a2a_server.py` 用 `returnImmediately=true` 和可控异步生成器固化了这条并发语义。

## 运行

```powershell
cd 09-A2A/a2a-practice
python -m pip install -e ".[dev]"
python -m a2a_lab.demo
python -m pytest -q
```

如果想启动真实 A2A HTTP 服务：

```powershell
python -m a2a_lab.a2a_server
```

## 建议阅读顺序

1. `lifecycle.py`：框架无关任务状态机、幂等索引、版本和有序事件。
2. `custom_http.py`：看私有接口需要自行约定多少发现、运行、查询、取消和游标字段。
3. `execution.py`：区分“协议 Task ID”与可幂等重放的“业务 Execution ID”。
4. `a2a_server.py`：看 Agent Card、Executor、TaskUpdater、Artifact 和官方路由如何组合。
5. `demo.py`：通过 ASGI 客户端完成能力发现和任务委托。
6. `tests/test_lifecycle.py`：先验证状态迁移、事件序号、租户隔离和幂等冲突。
7. `tests/test_custom_http.py`：观察私有协议为同一语义写了哪些代码。
8. `tests/test_a2a_server.py`：观察 A2A 的 submitted/working/completed/failed/rejected 与 Artifact。
9. `COMPARISON.md`：复述 A2A、MCP 和同进程多 Agent 的边界。

## 关键失败语义

| 场景 | Task 终态 | 是否重试原请求 |
|---|---|---|
| 输入含敏感明细或租户无权 | `rejected` | 否，需修改输入或授权 |
| 报告模型抛异常/超时 | `failed` | 可用同一业务请求创建受控重试策略 |
| 调用方主动取消 | `canceled` | 由用户决定是否新建任务 |
| 幂等键对应不同输入 | `rejected` / HTTP 409 | 否，修正调用方幂等键 |
| 任务成功并产生报告 | `completed` + Artifact | 重复委托直接重放 Artifact |

`rejected` 表示“服务理解了请求但不接受执行”，`failed` 表示“已经接受并执行但未成功”。把两者混成一个 500 会让调用方采取错误的重试策略。

项目只演示本地单进程传输，生产中仍要实现调用方身份、授权委托、租户隔离、超时、取消传播、artifact 下载权限、跨服务 trace 和持久化任务存储。

## 推荐实验

1. 运行同一幂等键两次，确认报告生成器只执行一次，第二次 Artifact 标记 `replayed=true`。
2. 用同一幂等键提交不同收入值，比较私有 HTTP 409 与 A2A `TASK_STATE_REJECTED`。
3. 给生成器注入超时和异常，检查终态是 `failed`，且响应/事件不含异常正文。
4. 请求 `/tasks/{id}/events?after=1`，理解事件游标与“只读当前 Task 快照”的差异。
5. 把内存账本替换成 SQLite，给 `(tenant, idempotency_key)` 建唯一约束，再测试并发提交。
6. 提交 `true`、`NaN` 与 `Infinity` 聚合值，确认 HTTP 与领域入口都稳定拒绝且不会创建任务。

## 真实模型实验

`build_a2a_app(report_generator=...)` 允许注入报告生成器，默认仍使用确定性实现。`tests_live/test_live_a2a_report.py` 注入真实模型并通过 A2A HTTP 边界检查 Task 与 Artifact。配置方式见 [统一 live 配置](../../shared/README.md)，运行 `python -m pytest -q tests_live -m live`。
