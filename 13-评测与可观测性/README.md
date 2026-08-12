# 13｜评测与可观测性

**安排：** 第 3 周开始，第 7 周集中完善，P0。

详细学习：[从 20 条样本建立第一个 Eval Harness](./01-Eval-Harness实操.md)。

配套工程：[eval-observability-practice](./eval-observability-practice/README.md)。它包含 20 条带证据约束的 JSONL golden set、数据集指纹、oracle 隔离输入、三个有版本号的确定性候选、严格 trace 身份/结构校验、工具执行状态与参数策略、完整 Span 图检查、Runner 实测 P50/P95、递归脱敏 artifact、tag/Wilson 切片、case/tag 级回归门，并提供带关键事实负例的严格 Pydantic LLM Judge live 测试。

快速开始：

```powershell
cd 13-评测与可观测性/eval-observability-practice
python -m pip install -e ".[dev,live]"
python -m eval_lab.demo
python -m pytest -q
```

## 零基础前置

数学只需比例、平均值和排序。先理解“固定 20 道题，每次改系统后重新考试”，再学习 precision/recall 和自动指标。不会写评测框架时可以先用表格人工打 0/1 分。

## 三层评测

1. **组件级**：解析、chunk、retrieval、rerank、工具选择、参数、SQL。
2. **轨迹级**：是否走对路径、是否重复调用、步骤/成本是否合理。
3. **端到端**：任务是否完成、答案是否正确、用户是否满意。

## 指标建议

| 对象 | 指标 |
|---|---|
| 检索 | Recall@k、Precision@k、MRR、nDCG |
| RAG | context precision/recall、faithfulness、answer relevancy、正确引用率 |
| Tool/Agent | tool selection、argument accuracy、goal success、steps、无效调用率 |
| NL2SQL | execution accuracy、结果集等价、权限违规率、扫描量 |
| 系统 | P50/P95、错误率、token/成本、恢复成功率、人工介入率 |

## Golden set

- 30～50 条起步，覆盖常见、边界、对抗、拒答和权限场景。
- 每条保存问题、期望答案/行为、证据、允许工具、禁止行为和难度标签。
- 数据集、prompt、模型、检索参数和代码一起版本化。
- LLM-as-a-Judge 需校准：抽样人工复核，记录 judge 模型和 rubric。

## Trace 最少字段

`trace_id`、`task_id`、用户/租户、模型/版本、prompt/context 版本、tool call、参数摘要、耗时、token、状态迁移、错误分类、重试、最终结果。禁止记录明文密钥和不必要的敏感数据。

## 评测报告结构

```text
目标与假设 → 数据集 → 实验配置 → 总指标
→ 分组指标 → 失败样本 → 原因分类 → 下一步实验
```

## 资料怎么用

| 优先级 | 资料 | 它是干什么的 | 零基础怎么使用 |
|---|---|---|---|
| P0 | [RAGAS Metrics](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/) | RAG/Agent 自动评测指标目录，说明每个指标需要什么输入、衡量什么 | 不要全学。先选 context recall、faithfulness、answer relevancy；每个指标手工检查 5 条结果，理解它何时会误判 |
| P1 | [DeepLearning.AI Evaluating AI Agents](https://www.deeplearning.ai/courses/evaluating-ai-agents) | 约两小时的视频课，介绍 trace、组件级 evaluator、LLM-as-a-Judge 和实验迭代 | 已经有可运行 Agent 后再看。边看边把课程方法映射到自己的 tool selection、参数和 goal success，不要只完成播放 |
| P1 | [Anthropic：Demystifying Evals for AI Agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents) | 多轮 Agent 评测、任务环境、grader 组合和生产迭代经验 | 先有 20 条样本；用代码规则、结果、轨迹、LLM Judge、人工混合，不依赖单一分数 |

零基础最先做的评测不是安装 RAGAS，而是拿 20 条固定问题人工判断成功/失败并分类原因。工具只是把已经想清楚的标准自动化。
