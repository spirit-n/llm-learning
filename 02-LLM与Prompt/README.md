# 02｜LLM 基础与 Prompt Engineering

**安排：** 第 1 周半天，P0；后续并入 Context Engineering。

详细学习：

- [大模型应用基础：一次请求发生了什么](./01-一次LLM请求发生了什么.md)
- [Prompt 实验手册](./02-Prompt实验手册.md)

## 零基础前置

你只需会 Python 字符串、list/dict、函数和 JSON；不会时回到 [Python 零基础语法](../01-Python工程基础/02-Python零基础语法.md)。本章暂时不需要机器学习公式，也不需要理解模型如何训练。

## 只学足够用的模型概念

- token、context window、输入/输出 token 与成本。
- system/user/assistant/tool 消息的职责。
- temperature、top-p、max tokens、stop 的影响。
- streaming、structured output、tool calling 的区别。
- 幻觉不是异常，而是生成目标与事实约束之间的结构性问题。

## Prompt 模板

```text
角色与边界：你负责什么，不负责什么
任务：当前要完成的单一目标
上下文：可信材料、状态和工具结果
规则：权限、安全、拒答、引用要求
输出契约：JSON Schema 或清晰格式
示例：只在能显著消除歧义时提供
```

## 四个已配套实验

1. [实验一](./03-Prompt实验一.ipynb)：模糊指令 vs 明确任务/边界/JSON 契约，分别观察 API、格式与业务成功。
2. [实验二](./04-Prompt实验二.ipynb)：zero-shot vs few-shot，固定样本和指标后比较收益与输入成本。
3. [实验三](./05-Prompt实验三.ipynb)：冲突材料与来源优先级，不把“都答对”直接解释为规则有效。
4. [实验四](./06-Prompt实验四.ipynb)：Prompt 注入与安全边界，区分提示约束和代码强制控制。

压缩与任务恢复实验移到 [第 10 章](../10-Context-Engineering/README.md)，不覆盖已经跑过的 notebook 和结论。

2026-10-04 接口补充：采样参数、工具、原生结构化输出、推理预算是**具体端点＋模型**的能力，不保证所有兼容接口都支持。温度为 0 不保证绝对复现或答案正确；流式主要改善可见首字等待。可选 Responses 对照、结束原因与用量记录见 [共享接入说明](../shared/README.md)。现有四项模型环境变量保持不变。

## 运行实验前的模型配置

四个 Prompt notebook 与后续工程共用 [真实模型统一配置](../shared/README.md)，代码不内置 provider、端点、模型名或 key。至少显式设置：

```powershell
$env:LLM_BASE_URL = "https://provider.example.com/v1"
$env:LLM_MODEL = "provider-model-name"
$env:LLM_API_KEY_ENV = "PROVIDER_API_KEY"
$env:PROVIDER_API_KEY = "你的密钥"
```

也可以直接设置 `LLM_API_KEY`，或者用完整的 `LLM_CHAT_COMPLETIONS_URL` 代替 `LLM_BASE_URL`。缺少任一必要配置时，notebook 会在第一段代码直接报错，不会发送请求。

## 不要浪费时间

- 背“万能提示词”。
- 要求模型输出隐藏思维过程。
- 认为更长 prompt 必然更好。
- 用 prompt 代替权限、SQL 校验、参数验证和结果验证。

## 面试表达

> Prompt Engineering 主要设计指令与输出约束；Context Engineering 决定模型在正确时刻看到哪些系统规则、业务知识、历史、检索结果、工具结果和运行状态。前者是后者的一部分。

## 资料怎么用

| 优先级 | 资料 | 它是干什么的 | 零基础怎么使用 |
|---|---|---|---|
| P0 | [Anthropic Prompt Engineering](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/overview) | 官方 Prompt 方法，讲如何先定义成功标准、设计清晰指令、示例、格式和评测 | 不要求使用 Claude。先读 Overview 和 best practices；每读一个技巧就在 20 条小数据集上验证，不能只抄模板 |
| P2 | [Hugging Face NLP Course](https://huggingface.co/learn/nlp-course/) | 系统介绍 NLP、tokenizer、Transformer 和 Hugging Face 工具生态 | 内容较多，不适合第 1 周通读。先看 tokenization/Transformer 的概念章节；训练代码等第 8 周再回来看 |
| P1 | [Microsoft Generative AI for Beginners](https://github.com/microsoft/generative-ai-for-beginners) | 微软 21 课生成式 AI 课程，覆盖基础、Prompt、RAG、Function Calling、安全等 | 先选基础和 Prompt 课程；云服务代码可只阅读，概念转成自己的小实验 |

先完成本目录两篇中文笔记和 Prompt 实验，再打开官方资料。看到公式或训练代码卡住可以先跳过，不影响应用开发主线。
