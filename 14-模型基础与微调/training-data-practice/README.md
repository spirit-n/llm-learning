# 训练前的数据与损失掩码检查（离线）

无需 GPU、模型下载、Transformers 或 TRL。使用可见的字符级教学 tokenizer 和角色模板，检查 messages/tools/tool_calls/tool result 的关联、assistant-only labels、EOS、padding 与超长拒绝。

```powershell
python -m pip install -e ".[dev]"
python -m training_data_lab.data
python -m pytest -q
```

这不是模型训练或通用 JSON Schema validator：参数检查只覆盖 required/额外字段；真实训练必须用完整 schema 校验和目标模型 tokenizer。字符数也不等于真实模型 token 数。数据已用明确角色控制标签，user/system/tool 内容均不进入 loss；assistant 的调用参数和最终答复进入 loss。实际 causal LM 通常在模型内部做 labels shift，不能再手工移一遍。

## 可选：迁移到真实 TRL/PEFT

1. 单独训练环境固定 TRL/Transformers/PEFT/torch 兼容版本，不覆盖应用工程环境。
2. 使用目标模型 chat template、EOS 与 generation mask；`assistant_only_loss=True` 需要模板支持 generation 边界。检查非 assistant labels 均为 `-100`，也检查 assistant 有非空监督，不能只看 loss 下降。
3. prompt-completion 与完整 conversational 数据的默认 loss 范围不同；明确选择 completion-only 或 assistant-only。工具样本包含 `messages`、`tools`、`tool_calls` 和 tool 结果。
4. 保存 adapter、基础模型 revision、tokenizer/template、数据指纹与评测结果；adapter 本身不是完整基础模型。
5. 小规模 smoke training 后比较无微调基线、安全/工具参数准确率，再决定是否扩大。不要直接照搬 main 文档的新参数到旧版本。

来源（核对日期 2026-10-04）：[TRL SFT，main 为开发文档](https://huggingface.co/docs/trl/main/en/sft_trainer)、[PEFT checkpoint](https://huggingface.co/docs/peft/en/developer_guides/checkpoint)。
