# 14｜Transformer 与微调

**安排：** 第 3～4 周各穿插 60～90 分钟概念卡，第 8 周用 2 天整理面试表达，P2。目标是理解应用选型并能讲清，不做从零训练。

详细学习：

- [Transformer 通俗但准确的解释](./01-Transformer详解.md)
- [微调、LoRA 与实验流程](./02-微调流程详解.md)
- [本地与云端微调实验方案](./03-本地与云端实验方案.md)

## 零基础前置

先有 token、向量和概率的直觉即可。公式看不懂时先读文字与图，不影响应用工程主线。微调实操需要额外 GPU/云资源时可以只完成流程、数据和评测设计，不必为了“跑过”盲目花钱。

## 分阶段怎么学

- 第 3 周：读 Transformer 教程的 token、embedding、attention、上下文窗口和 decoder-only，只联系 RAG 现象，不推公式。
- 第 4 周：读微调教程的预训练、SFT、LoRA/QLoRA 和“RAG 还是微调”，不启动高成本训练。
- 第 8 周：把前两次笔记压缩成 5 分钟讲解、选型表和常见追问答案；只有目标 JD 明确要求时才做 LoRA 最小实验。

当前设备建议：先用带 RTX 3050 Ti 的笔记本完成小模型 LoRA/QLoRA 闭环；GTX 1050 Ti 只作兼容性备用，不建议把 RX 5700 XT 的非官方 ROCm 适配当作学习主线。需要做 3B/7B 模型、较长上下文或多组对比实验时，再按小时租 24 GB NVIDIA 云卡。具体边界和检查命令见[本地与云端微调实验方案](./03-本地与云端实验方案.md)。

## Transformer 五分钟版本

- token 经 embedding 变成向量，位置编码/位置机制表达顺序。
- Self-Attention 用 Query、Key、Value 建模 token 间关系；缩放点积后 softmax 得到权重。
- Multi-Head 让模型在不同子空间学习关系；残差、归一化和 FFN 支撑深层训练。
- Decoder-only 模型以自回归方式预测下一个 token，用 causal mask 禁止看未来。
- 推理能力还受训练数据、目标、对齐、上下文和工具系统影响，不能把 Agent 能力归因于 Attention 一项。

## 微调流程

```text
定义任务与基线 → 收集/清洗/去重 → 格式化数据
→ train/valid/test 隔离 → SFT 或 LoRA/QLoRA
→ 离线评测/安全评测 → 灰度 → 监控 → 回滚
```

## RAG 与微调怎么选

| 需求 | 优先方案 |
|---|---|
| 更新频繁、需引用、需权限隔离的知识 | RAG |
| 工具执行与实时数据 | Tool/Agent |
| 固定风格、格式、分类、领域行为 | Prompt 基线后考虑微调 |
| 小模型领域适配/私有部署 | PEFT/LoRA 候选 |

微调不能天然保证事实正确，也不适合把不断变化的知识“训练进去”。先建立无微调基线和评测集，否则无法证明收益。

## 面试追问

- LoRA 为什么能减少可训练参数？QLoRA 多了什么？
- SFT 数据质量怎样检查？数据泄漏怎样避免？
- 为什么验证集提高但线上效果可能下降？
- 量化、蒸馏、微调分别解决什么问题？

## 资料怎么用

| 优先级 | 资料 | 它是干什么的 | 零基础怎么使用 |
|---|---|---|---|
| P1 | [The Illustrated Transformer](https://jalammar.github.io/illustrated-transformer/) | 用大量图解释 encoder/decoder、attention、Q/K/V 和 Transformer 数据流 | 第 8 周配合中文笔记看图。第一遍只理解 token 如何互相“关注”和逐步生成，不要求推导矩阵公式 |
| P2 | [Hugging Face PEFT](https://huggingface.co/docs/peft/) | 参数高效微调库文档，覆盖 LoRA 等方法的配置、训练和模型加载 | 先读 conceptual guides/LoRA，再跑小模型示例。不要一开始下载大模型；先明确显存、数据和评测 |
| P2 | [LLaMA-Factory](https://github.com/hiyouga/LLaMA-Factory) | 将数据准备、LoRA/QLoRA、训练、评测、导出等流程封装成工具 | 先读 README 的支持范围和 Quickstart，做一次最小可复现实验。它降低操作门槛，不替你解决数据质量和评测问题 |

若你的目标是应用工程岗，先做到能讲清流程和选择依据。没有 GPU 也可以完成这一章的核心面试目标。
