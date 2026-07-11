# Transformer 通俗但准确的解释

## 1. 输入表示

文本先分 token，查 embedding 矩阵得到向量。模型还需要位置信息，否则“我打你”和“你打我”仅看 token 集合相同。现代模型的位置机制可能不同，面试先讲清“为何需要顺序信息”，再按具体模型补充。

## 2. Self-Attention

每个 token 向量经不同线性变换得到 Q、K、V：

```text
Attention(Q,K,V) = softmax(QKᵀ / √d) V
```

Q 表示“我在找什么”，K 表示“我能被怎样匹配”，点积得到相关权重，再对 V 做加权汇总。`√d` 缩放帮助数值稳定。

这只是直觉，不能说 Q/K/V 分别是固定的“问题/关键词/答案”；它们是训练学得的向量投影。

## 3. Multi-Head、残差和 FFN

多头在不同投影空间并行学习关系，再拼接。残差让信息和梯度更容易传递，LayerNorm 稳定训练，FFN 对每个位置做非线性变换。一个 Transformer block 反复堆叠这些组件。

## 4. Decoder-only

生成模型使用 causal mask，让当前位置不能看到未来 token。训练时预测下一个 token；推理时一次生成一个/一批 token，并使用 KV cache 避免重复计算历史 K/V。

## 5. 与应用工程的联系

- context window 有限 → 需要 Context Engineering。
- embedding 表示语义 → 支撑 dense retrieval，但不擅长所有精确词项。
- 自回归生成有不确定性 → 需要 schema、tool、verifier 和 eval。
- KV cache/序列长度影响延迟与显存 → 长 prompt 有工程成本。

## 6. 自测

不用公式回答：Attention 为什么要位置？为什么除以根号维度？多头与单头差异？causal mask 做什么？KV cache 为什么能加速推理但增加显存？

资料：[The Illustrated Transformer](https://jalammar.github.io/illustrated-transformer/)。
