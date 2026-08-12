# LangChain 核心抽象与受控 Agent 练习

这个项目的默认 demo 和测试可完全离线运行。它使用真正的 LangChain Messages、Prompt、Tool、Agent、Retriever 和 Runnable API，同时补上框架不会自动提供的业务权限、工具预算、停止条件、结构化失败和审计事件。默认模型是可预测的 `DemoChatModel`；`tests_live/` 才接入环境变量配置的真实模型。

## 架构与边界

```text
question
  → runtime（输入限制、wall-clock deadline、工具预算、任务完成契约、审计结果）
  → create_agent（消息循环与 Tool 调度）
  → LangChain Tool adapter
  → domain（tenant/role/指标版本，完全不依赖 LangChain）
```

| 模块 | 负责 | 关键边界 |
|---|---|---|
| `domain.py` | 指标契约、Catalog、tenant/role 权限 | 模型不能传入或提升自己的权限 |
| `tools.py` | Pydantic 参数 schema、工具适配、调用预算 | 预算在业务调用前消耗 |
| `model.py` | 确定性正常模型与故意死循环模型 | 只用于离线复现控制流 |
| `agent.py` | `create_agent` 组装与依赖注入 | 不塞业务规则 |
| `runtime.py` | 输入拒绝、wall-clock timeout、recursion limit、工具上限、完成契约、错误归一化、审计事件 | 模型直接作答不能伪装成任务完成 |
| `retriever.py` | LangChain Retriever 接口、tenant/source 过滤、分数 metadata | 教学词项分数不是生产 embedding |
| `structured.py` | 严格结构化解析，并保留解析失败 | 不用正则猜测修复模型语义 |
| `runnables.py` | normalize、route、request pipeline、streaming | Runnable 不代替授权与校验 |

## 运行

```powershell
cd 05-LangChain/langchain-practice
python -m pip install -e ".[dev]"
python -m lc_lab.demo
python -m pytest -q
# 安装后也可以：langchain-demo
```

## 建议阅读顺序

1. `src/lc_lab/domain.py`：先看脱离框架也成立的业务契约和权限。
2. `src/lc_lab/tools.py`：看普通函数怎样变成带 schema 和预算的 Tool。
3. `src/lc_lab/model.py`：比较正常离线模型与永不停止的模型。
4. `src/lc_lab/agent.py`：`create_agent` 怎样注入 model、context 和 tool。
5. `src/lc_lab/runtime.py`：看应用边界怎样限制 Agent 并产生审计记录。
6. `src/lc_lab/structured.py`、`retriever.py`、`runnables.py`：再学独立组件。
7. `tests/test_langchain_practice.py`：主路径；`test_runtime_and_boundaries.py`：失败和越权路径。

## 你要观察什么

- 业务函数本身不依赖 LangChain，Tool 只是适配层。
- `tenant` 和 `roles` 由可信运行时绑定，不出现在模型可填写的 tool schema 中。
- Agent 替你维护消息循环，但不会替你实现权限、预算、幂等和业务校验。
- `DemoChatModel` 可换成真实 provider；工具和上层调用方式不用整体重写。
- 流式输出只是返回方式变化，不代表结果自动可靠。

## 已覆盖的失败场景

- 空问题、超长问题在模型调用前拒绝。
- 非规范指标名、缺少参数、多余字段由 Pydantic schema 拒绝。
- 不同 tenant 不回退查找；普通 analyst 访问 admin 指标会返回权限错误。
- 工具调用预算在真正执行前检查；故意循环的模型能被工具预算或图递归上限停止。
- 整个 model→tool 循环受 `wall_clock_timeout_seconds` 约束，慢模型和慢工具都归一化为 `AGENT_TIMEOUT` 并写入 Trace。
- 指标任务要求 `get_metric_definition` 至少产生一条成功工具结果；模型绕过工具直接“猜答案”会得到 `REQUIRED_TOOL_EVIDENCE_MISSING`，而不是 `completed`。
- `NOT_FOUND` 走明确拒答，而不是由模型补一条“看起来合理”的定义。
- 审计事件记录 tool call、tool result、final answer，并截断/脱敏敏感指标名。
- Retriever 在召回阶段做 tenant/source 过滤，并把教学分数放入 metadata。
- 结构化输出错误作为结果返回，调用方可以重试、降级或进入人工队列。

## 推荐实验

1. 先运行 `LoopingChatModel` 测试，分别调整 `max_tool_calls` 与 `recursion_limit`，观察两层停止条件。
2. 新增一个 tenant 私有指标，验证 schema 中没有 tenant/role，且跨租户始终查不到。
3. 给 Retriever 增加同义词或真实 embedding，但保持 metadata 过滤测试不变。
4. live 测试里故意问不存在的指标，检查真实模型会不会绕过 `NOT_FOUND` 编造答案。

## 教学实现的边界

- `DemoChatModel` 用规则产生 tool call，只验证框架控制流，不代表真实模型质量。
- 词项 Retriever、内存 Catalog 和进程内预算不具备分布式一致性。
- 本例的线程 deadline 能及时释放调用方，但 Python 无法安全强杀已开始的线程，所以工具刻意保持只读。生产还要把同一 deadline 传入模型 HTTP 和工具 I/O，让底层请求可取消；有副作用的工具必须使用幂等键/事务。
- 审计事件用于学习；生产日志还需 request ID、trace/span、持久化、访问控制和数据保留策略。

## 真实模型实验

`tests_live/test_live_tool_calling.py` 把 LangChain Tool 生成的 schema 发给真实模型，执行模型返回的 tool call，再把工具结果回填给模型。provider、端点和模型名不写死，配置方式见 [统一 live 配置](../../shared/README.md)：

```powershell
python -m pip install -e ".[dev,live]"
python -m pytest -q tests_live -m live
```
