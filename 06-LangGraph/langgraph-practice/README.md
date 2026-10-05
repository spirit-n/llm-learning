# LangGraph 可恢复、可审计的 SQL 工作流练习

正常运行统一使用 `192.168.11.8:3306` 的持久化 MySQL；配置与安装说明见 [共享数据库文档](../../shared/database/README.md)。先执行 `python -m pip install -e ../../shared/database`，再安装本工程。离线测试显式使用临时 SQLite 或内存。

## MySQL 跨进程恢复

```powershell
python -m pip install -e ../../shared/database
python -m pip install -e ".[dev,persistence]"
python -m lg_lab.persistent_demo pause --thread lesson-1
python -m lg_lab.persistent_demo approve --thread lesson-1
python -m pytest tests/test_persistence.py -q
```

同一个 thread ID 在两个独立进程间恢复。`persistent_demo` 默认读取 `DATABASE_URL`；checkpoint 和结果台账写入 MySQL。第一次 `paused=true`，审批后 `status=completed`，台账累计增加一条；重做请换 thread ID。测试覆盖结果已提交、checkpoint 尚未提交时崩溃后的回放。显式传入 SQLite 文件路径仅用于离线测试。

普通内存 demo 继续用于图结构讲解；持久化示例不调用真实模型，但会连接配置的 MySQL。外部 HTTP/退款/邮件副作用仍需下游幂等或 outbox。不要读取不可信来源的 checkpoint。

## 架构与模块边界

| 模块 | 责任 | 为什么单独存在 |
|---|---|---|
| `state.py` | 版本化、可序列化状态；v0→v1 迁移；`trace/error_history` reducer | checkpoint 不能保存数据库连接等运行时对象 |
| `nodes.py` | 单节点状态迁移、路由、HITL、重试和验证 | 节点只返回增量事件，循环不会复制整段历史 |
| `sql_policy.py` | SQLGlot AST、单条 SELECT、通配符/表/LIMIT 策略、SQL 指纹 | 生成 SQL 的模型不能给自己放行 |
| `warehouse.py` | `Warehouse` 端口和确定性离线实现 | 数据库可以替换；idempotency key 防止恢复时重复执行 |
| `graph.py` | 节点/边组装、checkpointer 和外部依赖注入 | 工作流拓扑与业务实现分离 |

```text
START → validate → classify
                    ├─ knowledge ─────────────────────────────→ answer → END
                    └─ data → schema → draft_sql → guard
                                                ├─ 拒绝 ─────→ answer → END
                                                └─ 通过 → review(interrupt)
                                                          ├─ 拒绝 → answer → END
                                                          └─ 批准 → execute
                                                                      ├─ 瞬时失败且有预算 → execute
                                                                      ├─ 失败/耗尽 → answer
                                                                      └─ 成功 → verify → answer
```

## 运行

```powershell
cd 06-LangGraph/langgraph-practice
python -m pip install -e ".[dev]"
python -m lg_lab.demo
python -m pytest -q
# 安装后也可以：langgraph-demo
```

## 建议阅读顺序

1. `src/lg_lab/state.py`：先看档案袋字段及 reducer，分清任务状态与运行时依赖。
2. `src/lg_lab/sql_policy.py`：看确定性 Guard 检查哪些 SQL 形状。
3. `src/lg_lab/warehouse.py`：看执行端口、瞬时错误和幂等缓存。
4. `src/lg_lab/nodes.py`：逐节点看错误码、重试条件、interrupt 和结果验证。
5. `src/lg_lab/graph.py`：看固定边、条件边、回边和依赖注入。
6. `src/lg_lab/demo.py`：观察首次暂停、相同 `thread_id` 恢复和完整 Trace。
7. `tests/test_workflow.py`：主路径；`test_policy_and_resilience.py`：策略与恢复边界。

## Checkpoint 边界

`InMemorySaver` 只适合本地学习和测试。生产环境需换持久化 checkpointer，并认真设计 thread ID、数据保留和节点幂等。

## 已覆盖的失败/边界场景

- 空问题、过长问题、非法重试策略会在进入模型/数据库路径前失败。
- 无授权表时 schema 节点直接拒绝，不进入 SQL 生成或人工审核。
- Guard 使用 SQLGlot AST 拒绝写语句、多语句、`SELECT *`、`alias.*`、`COUNT(*)`、未知表、缺失/过大 LIMIT；换行、注释和大小写不能绕过通配符检查，字符串里的关键字不会误报。
- `state_version=0` 的旧 checkpoint 会显式迁移旧重试/表字段并记录 `state:migrated:v0->v1`；高于当前版本的状态返回 `UNSUPPORTED_STATE_VERSION`，不会猜测未来字段。
- interrupt payload 包含风险等级和 SQL 指纹；只接受布尔恢复值，用户拒绝得到明确 `cancelled` 终态。
- 数据库瞬时错误最多尝试指定次数，错误历史保留 retryable 标志；权限/策略错误不重试。
- `request_id + SQL 指纹` 组成 execution key，让 checkpoint 重放命中同一结果；独立请求不会误共享缓存。
- 空结果和越界成功率不能直接生成答案，必须经过 `verify`。
- reducer 测试确认循环只追加事件；checkpoint history 和 stream update 可用于定位节点。

## 推荐实验

1. 运行 `failures_remaining=1/3/5`，比较最终状态、attempts、错误历史和 Trace。
2. 在 `inspect_sql` 测试中加入 JOIN、子查询、alias wildcard 和注释绕过样本，观察 AST 节点而不是正则文本。
3. 阅读 `PersistentWarehouse` 的 MySQL 执行、行锁和持久化台账，保持 `Warehouse.query`、幂等键和测试夹具不变。
4. 将 `InMemorySaver` 换持久化 checkpointer，结束进程后用同一 thread ID 恢复。
5. live 生成节点故意请求危险 SQL，确认无论模型如何回答都必须经过同一个确定性 Guard。

## 教学实现的边界

- `sql_policy.py` 已使用 SQLGlot AST，但仍只是应用层 allowlist；生产还需数据库只读账号、statement timeout、扫描量限制，并固定实际数据库 dialect 做回归测试。
- `DemoWarehouse` 的缓存只在单进程内有效，生产幂等记录应持久化并设置生命周期。
- 示例 retry 不真实 sleep，生产要结合错误类型做有限退避，并把总时限纳入预算。
- `InMemorySaver` 不提供跨进程恢复、加密或 TTL；本例只演示单步 v0→v1 迁移，生产还要维护逐版本迁移链和回滚策略。

## 真实模型实验

`tests_live/test_live_sql_node.py` 让真实模型承担 `draft_sql` 节点，再把输出送入确定性的 `sql_guard`。这能直观看到“LLM 负责生成候选、代码负责安全边界”。端点、模型和 Key 均不写死，配置方式见 [统一 live 配置](../../shared/README.md)：

```powershell
python -m pip install -e ".[dev,live]"
python -m pytest -q tests_live -m live
```
