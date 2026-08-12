# Eval Harness 与 Trace 练习

这个工程使用 20 条固定 golden set，对同一个指标 Agent 的 `baseline`、`candidate` 和故意损坏的 `broken` 版本做离线评测：

```text
Validated JSONL + fingerprint → versioned Agent Trace
→ oracle-isolated EvalInput → validated/version-bound Agent Trace
→ behavior/answer/tool status/args/trajectory/evidence/trace/safety evaluators
→ weighted aggregate + tag slices + confidence interval
→ policy regression gate → recursively redacted JSON/JSONL/Markdown artifacts
```

默认不调用模型。`tests_live/` 额外验证一个可配置的 LLM Judge 是否遵守由 Pydantic 生成的严格 JSON 契约，以及它能否拒绝“关键词都存在、关键事实却颠倒”的答案；确定性 evaluator 仍是主要验收依据。

## 关键可信边界

```text
EvalCase（含期望答案/禁止工具等 oracle，只属于 Harness）
        │ 只投影 case_id + user_input
        ▼
EvalInput（冻结） → 被测系统 → 未信任返回值
                               │ Pydantic 结构校验
                               │ case_id / variant / system_version 绑定
                               │ Runner 外层实测 latency
                               ▼
                          AgentTrace → Evaluators
```

- 被测系统永远收不到完整 `EvalCase`，不能读取答案或篡改评分标准。
- 一个 case 抛异常、返回错结构、串了缓存 trace 或复用了 trace ID，只会转成该 case 的错误结果，不会中断整批；case ID 重复则在开跑前拒绝。
- 工具选择正确不等于执行成功：`tool_execution` 单独要求所有调用 `status="ok"`。
- 参数默认 `argument_match="exact"`，多一个参数也失败；确需只检查子集时必须在样本中显式写 `contains`。
- Span 图必须只有一个根、无环，且所有节点都可达；工具 span 还要按名称、状态和参数覆盖 tool call。
- 内存 trace 用于评分，写盘前报告与逐条 trace 统一递归清洗 output、嵌套 tool args 和敏感自由文本。

## 运行

```powershell
cd 13-评测与可观测性/eval-observability-practice
python -m pip install -e ".[dev,live]"
python -m eval_lab.demo
python -m pytest -q
```

需要生成报告时显式指定目录：

```powershell
python -m eval_lab.demo --output-dir artifacts/eval-run
```

真实 Judge 使用 [统一模型配置](../../shared/README.md)：

```powershell
python -m pytest -q tests_live -m live
```

## 阅读顺序

1. `evals/datasets/metric_agent_v1.jsonl`：先看 20 条题目如何表达期望行为、工具、参数和禁止动作。
2. `src/eval_lab/dataset.py`：逐行错误定位与规范化数据集指纹。
3. `src/eval_lab/models.py`：数据集语义约束、trace/span、分数、报告和 Gate Policy 契约。
4. `src/eval_lab/app.py`：三个有版本号的确定性系统怎样稳定制造改进与回归。
5. `src/eval_lab/evaluators.py`：行为、答案、完整工具序列、参数、轨迹、证据、span 图和安全怎样独立评分。
6. `src/eval_lab/runner.py`：单条异常保留、加权聚合、Wilson 区间、case/tag 级回归门。
7. `src/eval_lab/tracing.py`：trace/span 的父子关系、类型和统一递归脱敏。
8. `src/eval_lab/reporting.py`：以 run ID 保存不可覆盖的 JSON、trace JSONL 和 Markdown。
9. `src/eval_lab/judge.py`：由 Pydantic schema 生成 Judge 输出契约并严格验收。
10. `tests/` 与 `tests_live/`：26 条离线验收，以及 Judge 正例/关键事实负例。

## 当前离线结果

| 版本 | Goal success | Safety | P95 延迟 |
|---|---:|---:|---|
| `baseline` | 65% | 95% | Runner 调用边界外实测，随机器变化 |
| `candidate` | 100% | 100% | Runner 调用边界外实测，随机器变化 |

baseline 的 7 个失败分别覆盖工具选择、答案错误、跨租户参数、安全工具、重复轨迹、证据缺失和 provider 断连；candidate 会在相同数据集指纹下全部修复。Gate 同时检查最低质量/安全阈值、P95、case 级退化和 `safety/permission/secret` 保护切片，避免总平均值掩盖小切片问题。

这些质量数值用于练习报告和回归门，不代表真实线上性能。确定性 Demo 几乎没有 I/O，延迟主要是计时器噪声，不应用来做性能结论；换成真实系统后仍由 Runner 用相同边界实测。4/4 的切片虽然是 100%，Wilson 95% 区间下界仍明显低于 100%，这正是小样本不能写“已经证明稳定”的原因。

## 建议实验

1. 把 candidate 的 q18 证据去掉，观察只有 `evidence` evaluator 失败，而其他组件仍通过。
2. 复制一个安全样本并让候选误调用写工具，观察保护切片和 case regression 如何双重拦截。
3. 修改一条数据后错误地拿旧 baseline 比较，确认 Gate 因 dataset fingerprint 不同而拒绝。
4. 显式生成两次报告，确认 run ID 让历史 JSON 和 trace JSONL 不会互相覆盖。
5. 让一个假系统返回别的 case/variant/version 的 trace，观察它只变成当前 case 的 `TraceContractError`。
