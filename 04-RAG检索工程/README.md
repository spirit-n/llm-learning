# 04｜RAG 与检索工程

**安排：** 第 2～3 周，P0，8 周路线中的第一重点。

详细学习：

- [从零搭建 RAG 的每一步](./01-从零搭建RAG.md)
- [RAG 实验、指标与失败分析](./02-RAG实验手册.md)

微软教程补充：先按 [LangChain 导读](../05-LangChain/02-微软LangChain教程导读.md) 学文档、Embedding、语义检索，再按 [AI Agents 导读](../06-LangGraph/02-微软AI-Agents教程导读.md) 学 Agentic RAG；固定 RAG 基线没有评测前，不做 Agentic RAG。

## 零基础前置

需要会读写文本/JSON、list/dict、函数和最基本的 HTTP/API 概念。向量、相似度、BM25 等会在本章逐步建立直觉，不要求提前学习线性代数。先查 [基础术语表](../00-学习规划/基础术语表.md) 中的 RAG 部分。

## 全链路

```text
数据源 → 解析/清洗 → chunk + metadata → embedding/index
用户问题 → query rewrite（可选）→ dense + sparse 召回
→ RRF 融合 → reranker → 去重/过滤 → Context Builder
→ 带证据生成 → 评测、trace、反馈
```

## Chunk 不是固定答案

至少比较四种策略：固定 token、递归字符、标题层级、parent-child。记录 chunk 长度、overlap、文档类型、Recall@k、上下文噪声和成本。代码、表格、FAQ 与普通段落不能机械使用同一策略。

## 为什么不只用向量检索

- Dense 擅长语义改写，但可能漏掉错误码、型号、缩写、专有名词。
- BM25/稀疏检索擅长精确词项，但不理解同义表达。
- Hybrid 提高候选召回；RRF 融合不同分数空间中的排名。
- Reranker 在较小候选集上做更贵的相关性判断，主要改善精度。

## 实验矩阵

| 版本 | 召回 | 重排 | 要回答的问题 |
|---|---|---|---|
| A | dense | 无 | 最小基线多差？ |
| B | BM25 | 无 | 精确术语是否更好？ |
| C | dense + BM25 + RRF | 无 | recall 是否提高？ |
| D | hybrid | reranker | precision 与端到端质量是否提高？ |

至少记录 Recall@5/10、MRR 或 nDCG、context precision/recall、faithfulness、answer relevancy、P50/P95 延迟和单请求成本。

## 失败分类

1. 解析错：正文缺失或表格损坏。
2. 切分错：证据被切断或 chunk 噪声太大。
3. 召回错：正确证据不在候选集。
4. 排序错：证据存在但排名太后。
5. Context 错：重复、冲突、过长或权限泄露。
6. 生成错：模型未忠于证据或引用错误。

## 生产问题

- 文档版本、增量更新、删除与索引一致性。
- tenant/user/department 权限过滤必须在检索层执行。
- prompt injection 文档不能覆盖系统规则。
- 引用要绑定 chunk ID、源文档、版本和页码/标题。
- 多模态 RAG 作为选做：先解决图片/表格解析与跨模态评测，再谈模型。

## 资料怎么用

RAG 资料很多，按“先建立直觉 → 跑基线 → 做检索优化 → 做评测”的顺序使用。

| 阶段/优先级 | 资料 | 它是干什么的 | 零基础怎么使用 |
|---|---|---|---|
| 入门/P0 | [B站 RAG 实战](https://www.bilibili.com/video/BV1ug3qzhEp9/) | 中文视频，覆盖 RAG 原理、优化、召排、评估和项目示例，适合先建立全局印象 | 第一遍只看流程，不暂停抄代码；第二遍结合本目录笔记画出“文档进入—答案输出”的数据流。视频 API 可能过时，以官方文档为准 |
| 入门/P1 | [Advanced RAG 短课](https://www.deeplearning.ai/courses/building-evaluating-advanced-rag) | 介绍 sentence-window、auto-merging retrieval 和 RAG 评测思想 | 完成 Naive RAG 后再看，否则概念太多。重点记“为什么需要评测”和两种检索改进，不要求照搬其框架 |
| Embedding/P0 | [Sentence Transformers](https://www.sbert.net/) | 常用文本 embedding 与 reranker 库，能把句子变成向量并计算语义相似度 | 先看 Quickstart，运行两个句子的 embedding/相似度；训练模型章节先跳过 |
| Hybrid/P0 | [Qdrant Hybrid + Reranking](https://qdrant.tech/documentation/advanced-tutorials/reranking-hybrid-search/) | 一个完整的 dense + sparse/BM25 + RRF + reranker 官方教程 | 第 3 周使用。先看架构图和 Overview，再逐段运行；把每个阶段的输入/输出写在自己的笔记里 |
| RRF/P1 | [Qdrant RRF](https://qdrant.tech/documentation/search/hybrid-queries/) | 解释如何用 RRF 合并多路检索排名，以及 Qdrant 的 hybrid query 写法 | 先理解“按排名融合，而不是直接加不同分数”；公式暂时看不懂也没关系，先手算 3 个文档的小例子 |
| 评测/P0 | [RAGAS Metrics](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/) | 列出 RAG 和 Agent 常用自动评测指标，如 context precision/recall、faithfulness | 不要一开始全用。先选 context recall、faithfulness、answer relevancy 三个，逐个写清“高分代表什么、可能误判什么” |
| 框架对照/P2 | [LlamaIndex Starter Tutorial](https://developers.llamaindex.ai/python/framework/getting_started/starter_example/) | 从基本 Tool/Agent 进入 RAG，并提供完整的文档、索引、查询概念地图 | Naive RAG 后选看；理解 Document/Node/index/query 即可，不把主项目迁移到第二套框架 |

如果感觉这些名词一起出现太难，先只完成：解析 10 篇文档 → 固定 chunk → dense top-5 → 带引用回答。跑通后再加入 BM25、RRF、reranker。
