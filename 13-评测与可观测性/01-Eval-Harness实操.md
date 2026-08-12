# 从 20 条样本建立第一个 Eval Harness

配套可运行工程见 [eval-observability-practice](./eval-observability-practice/README.md)。项目已把本页目录、20 条数据、trace/span、多个 evaluator、聚合、回归门和报告生成落成代码。

## 1. 目录

```text
evals/
├── datasets/rag_v1.jsonl
├── runners/run_rag_eval.py
├── evaluators/retrieval.py
├── evaluators/answer.py
├── configs/baseline.yaml
├── results/
└── reports/
```

原始结果不要覆盖；结果文件名至少包含 run ID，并在报告内记录数据集指纹、代码/系统版本、模型、Prompt 和 config ID。配套工程会按 `<variant>-<run_id>` 同时保存完整报告和逐条 trace JSONL。

## 2. 样本字段

```json
{"id":"q1","input":"...","expected":"...","evidence_ids":["d1#c2"],"allowed_tools":[],"forbidden":[],"tags":["definition"]}
```

Agent 样本额外记录允许/期望工具、最大步骤、是否需要拒绝或人工确认。

## 3. Evaluator 选择

- 代码规则：schema、引用存在、工具名、参数范围、SQL 只读、步数。
- 执行评测：SQL 结果集等价，不要求字符串完全相同。
- 语义指标：回答相关性、faithfulness；记录 judge 版本/rubric。
- 人工：高风险、主观质量和自动指标分歧样本。

## 4. 最小运行循环

```python
for case in dataset:
    # 被测系统只拿公开输入，不能拿到 expected/forbidden 等评分 oracle。
    request = EvalInput(case_id=case.id, user_input=case.input)
    started = perf_counter()
    trace = validate_and_bind_trace(app.run(request), case, app.version)
    trace.latency_ms = (perf_counter() - started) * 1000  # Harness 外层实测
    scores = {name: evaluator(case, trace) for name, evaluator in evaluators.items()}
    save_raw(case, trace, scores)

aggregate_by_tag()
write_report()
```

捕获单条失败继续运行，同时标记系统错误；不要因为异常直接丢失最难的样本。返回 trace 还应校验结构，并绑定当前 `case_id`、候选 `variant` 和 `system_version`，防止缓存串样本或串版本；同一批次的 `trace_id` 也必须唯一。Runner 开始前应重新校验并快照数据集 oracle，拒绝重复 case ID，避免绕过 loader 或评测途中篡改标准。

总分之外还要保存组件分：行为对但工具错、工具名对但执行失败、答案对但证据缺失、结果对但调用轨迹失控，是不同的修复任务。工具参数要说明采用严格相等还是子集匹配，不能悄悄忽略额外参数。配套工程还会验证 Span 图只有一个根、无环、全部可达，并检查工具调用是否留下名称/状态/参数一致的 span，避免“业务通过、观测失明”。

## 5. 观察与评测如何连接

线上 trace 可筛出失败样本，经脱敏和人工标注后加入离线数据集。离线改进通过后灰度上线，再观察分布漂移。不要直接把用户敏感对话复制进公开 eval 集。

### Trace 与 Span

[Microsoft AI Agents in Production](https://github.com/microsoft/ai-agents-for-beginners/tree/main/10-ai-agents-production) 用 trace 表示一次完整任务，用 span 表示其中一次模型、检索或工具步骤。对应本项目：

```text
Trace: 用户的一次“查询近 7 天导航成功率”任务
├─ Span: 意图分类
├─ Span: schema/指标检索
├─ Span: SQL 生成
├─ Span: SQL Guard
├─ Span: ClickHouse Tool
└─ Span: 答案与引用生成
```

每个 span 至少记录开始/结束、状态、父子关系、组件/版本、耗时、输入输出摘要和错误码。敏感输入只记脱敏摘要或引用；完整报告、逐条 trace、output 和嵌套工具参数在落盘前都应走同一套递归脱敏规则。

[Anthropic 的 Agent Evals 指南](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents) 可作为 P1 补充：复杂 Agent 应混合代码规则、结果验证、轨迹检查、模型评分与人工评审，不能只用单一 LLM Judge。

## 6. Dashboard 最小指标

- 任务成功/失败/人工介入率。
- P50/P95 总耗时与各节点耗时。
- token/成本、工具调用数、重复调用率。
- RAG 无证据/低召回、SQL 拒绝和权限事件。
- 按模型、版本、任务 tag、租户分组。

## 7. 结论要求

不要写“效果很好”。应写：在什么数据集指纹、哪些系统/Prompt 版本、哪些 tag、指标从多少到多少、代价增加多少、哪些样本退化、置信度/样本限制是什么。回归门应同时看总指标、保护切片和逐 case 配对变化。
