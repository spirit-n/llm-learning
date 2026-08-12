# 可评测、可观测的 RAG 检索练习

这个项目把 RAG 拆成可独立替换和单测的工程模块。默认实现不需要 API Key、不会下载模型；`tests_live/` 才会使用统一环境变量调用真实模型。

```text
Document → 校验/标题感知 Chunk → 权限与版本过滤
→ dense + BM25 → RRF → rerank → 最终相关性门控 → Context Builder
→ 引用校验 → Recall/Precision/MRR/nDCG/标签切片
```

其中 dense 使用稳定的教学用特征哈希向量，只负责演示接口、混合检索和评测方法，不代表生产 embedding 质量。生产替换点是 `DenseIndex` 的 embedder，而不是重写整个 pipeline。

## 模块边界

| 模块 | 责任 | 不负责什么 |
|---|---|---|
| `models.py` | 文档、Chunk、命中、过滤条件、Trace、评测结果契约 | 检索算法 |
| `chunking.py` | 标题切分、长章节 overlap、稳定 ID/内容指纹 | PDF/HTML 解析 |
| `indexes.py` | dense、BM25、RRF、教学 rerank | 权限认证和答案生成 |
| `pipeline.py` | 输入校验、候选深度、阶段编排与耗时观测 | 隐藏失败或自动改权限 |
| `context.py` | 最终相关性门控、token 预算、去重、证据边界、注入标记、引用校验 | 判断业务事实是否正确 |
| `evaluation.py` | 排名指标、标签切片、输入对齐检查 | 用单一总分代替错误分析 |

## 运行

```powershell
cd 04-RAG检索工程/rag-practice
python -m pip install -e ".[dev]"
python -m pytest -q
python -m rag_lab.demo
# 安装后也可以：rag-demo
```

## 阅读顺序

1. `models.py`：先看各阶段输入/输出契约。
2. `pipeline.py`：看过滤、候选召回、融合、重排和 Trace 怎样组装。
3. `chunking.py`：看标题感知切分、长段 overlap、稳定 ID 和内容指纹。
4. `indexes.py`：比较 dense、BM25、RRF 的分数与排名语义。
5. `context.py`：看 token 预算、证据边界、注入标记和引用验证。
6. `evaluation.py`：看 Recall、Precision、MRR、nDCG 和 tag slice。
7. `tests/test_rag.py`：先读主路径；再读 `test_rag_boundaries.py` 的失败场景。

## 已覆盖的真实失败/边界场景

- 重复 `doc_id`、空 query、非法 top-k 和错误 chunk 配置会提前失败。
- 旧版本、其他 tenant、source allowlist 在召回阶段过滤，不能等生成后补救。
- 无词项命中时不拿零分文档凑 top-k；即使向量碰撞/RRF 产生正分，生成前仍检查有区分度的词项覆盖率。明显无关问题返回 `LOW_RELEVANCE` 和“证据不足”，不会把“候选第一名”误当成“确有证据”。
- Context 超预算会报告被丢弃的 chunk；疑似文档指令会标成不可信数据，伪造 evidence 分隔符会被转义。
- 生成引用若不属于本次 context，`validate_citations` 会指出伪造 ID。
- 每个检索阶段记录输入数、输出数和耗时，失败可定位到召回、融合或重排。
- 评测输入数量不一致会报错，结果同时提供整体指标与 tag 切片。

## 推荐实验

1. 固定 `GOLDEN_CASES`，分别运行 dense、BM25、hybrid、rerank，记录指标和阶段耗时。
2. 把 `candidate_multiplier` 从 1/3/5 改动，只改变一个变量，观察 Recall 与延迟。
3. 增加无答案、版本冲突、跨租户和 prompt injection 样本，确认不是只优化容易题。
4. 最后才替换真实 embedding/reranker；替换前后沿用同一 golden set 和过滤规则。

## 教学实现的边界

- 字符近似 token 数不等于真实模型 token；生产应注入模型对应 tokenizer。
- 特征哈希和词项 overlap reranker 不具备生产语义质量。
- 内存索引没有增量更新、删除事务、持久化与多进程一致性。
- 注入标记只提供信号，真正安全还需要系统提示、工具权限、输出验证和红队评测共同完成。

## 真实模型实验

`tests_live/test_live_rag_answer.py` 将本地检索出的 context 交给真实模型，并用同一个 `validate_citations` 严格验证：至少有引用且不存在任何伪造 ID，不再用“包含任意合法 ID”作为宽松通过条件。配置方式见 [统一 live 配置](../../shared/README.md)，端点、模型和 Key 均不写死：

```powershell
python -m pip install -e ".[dev,live]"
python -m pytest -q tests_live -m live
```

普通 `pytest` 不会运行 live 测试。
