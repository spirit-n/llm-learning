# RAG 实验、指标与失败分析

## 1. Golden set 格式

```json
{
  "id": "q-001",
  "question": "导航成功率如何定义？",
  "reference_answer": "...",
  "evidence_chunk_ids": ["doc1#c3"],
  "allowed_sources": ["metric-spec-v2"],
  "tags": ["definition", "exact-term"]
}
```

加入无答案、版本冲突、跨文档、多跳、权限隔离、错误码和长问题。30～50 条只是起点。

## 2. 先评检索，再评生成

- Recall@k：正确证据是否进入前 k。
- Precision@k：前 k 中有多少有用。
- MRR：第一个正确证据排多前。
- nDCG：多个不同相关度证据的整体排名。

如果 Recall@k 很低，先改解析、chunk、query 和召回；不要用生成 prompt 掩盖。

## 3. 四组对照

固定数据集、生成模型、prompt 和 top-k，只改变检索策略：dense、BM25、hybrid RRF、hybrid + rerank。运行至少三次或使用确定性设置，保存配置与原始结果。

## 4. 端到端指标

RAGAS 等自动指标可测 context precision/recall、faithfulness、response relevancy。它们不是绝对真相：记录 judge 模型和 prompt，抽样人工校准，并报告不一致样本。

## 5. 错误分析表

| query_id | 失败层 | 现象 | 根因证据 | 修复假设 | 实验结果 |
|---|---|---|---|---|---|
| q-001 | chunk | 定义被切断 | 正确段落跨两块 | 标题切分 | 待测 |

每次只改一个主要变量。优化后既报告提升，也报告退化的 tag 组。

## 6. 最终报告

必须包含：数据集、模型/版本、参数、硬件/服务环境、质量指标、P50/P95 延迟、成本、失败分布、至少 5 个具体样本、限制与下一步。
