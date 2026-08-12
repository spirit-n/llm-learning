# 03｜Function Calling / Tool Calling

**安排：** 第 1 周后半，P0。这是从聊天应用进入 Agent 的关键。

详细学习：[手写一个受控工具调用循环](./01-手写受控工具调用循环.md)。

配套代码：[受控 Tool Calling 练习项目](./tool-calling-practice/README.md)。项目使用 fake model、Pydantic、SQLGlot 和 SQLite，实现本章要求的三个工具及完整 Guard 测试。

微软教程补充：按 [LangChain 导读](../05-LangChain/02-微软LangChain教程导读.md) 学第 04 章，按 [AI Agents 导读](../06-LangGraph/02-微软AI-Agents教程导读.md) 学 Tool Use 设计模式；先手写循环，再看框架封装。

## 零基础前置

先确保会写普通 Python 函数、看懂 dict/JSON、用 Pydantic 定义字段并捕获异常。不熟悉时先完成 [Python 入门实验](../01-Python工程基础/python入门实验.ipynb)。这一章先用 fake model，不要求立刻申请付费 API。

## 核心流程

```text
用户请求 → 模型选择工具并生成参数 → 程序校验权限与参数
→ 执行工具 → 工具结果作为新消息 → 模型生成答案或继续调用
```

模型只“提议”调用，运行时才拥有执行权。任何高风险操作都不能因为参数来自模型就跳过校验。

## 必做工具

- `get_metric_definition(metric_name)`：读取指标口径。
- `describe_table(table)`：返回经过裁剪的 schema。
- `run_readonly_sql(sql, max_rows)`：只读查询。

## Guard 清单

- schema 严格、枚举优先、字符串长度限制。
- 工具白名单与用户权限绑定。
- SQL AST/语义校验；禁止写操作、多语句和危险函数。
- timeout、limit、扫描量/成本限制、并发限制。
- 工具输出大小限制、敏感字段脱敏、审计日志。
- 循环最大步数、重复调用检测、幂等键。

## 必做实验

手写一个不依赖框架的 tool loop，并测试：未知工具、参数缺失、参数注入、工具超时、重复调用、结果过长、模型无休止循环。

## 评测

- 工具选择准确率
- 参数 exact/semantic match
- 工具执行成功率
- 平均调用次数和无效调用率
- 端到端任务成功率

## 资料怎么用

| 优先级 | 资料 | 它是干什么的 | 零基础怎么使用 |
|---|---|---|---|
| P0 | [LangChain Tools](https://docs.langchain.com/oss/python/langchain/tools) | 展示如何把普通 Python 函数声明成模型可选择的 Tool，以及工具参数和返回值如何表达 | 先学会普通 Python 函数和 Pydantic，再看页面中的最小 `@tool` 示例。只理解 tool schema 和调用流程，不急着搭完整 Agent |
| P1 | [DeepLearning.AI Function Calling 课程](https://www.deeplearning.ai/courses/function-calling-and-data-extraction-with-llms) | 约一小时的视频课，帮助建立“模型生成函数参数、程序执行函数”的直觉，并介绍结构化抽取 | 先看概念视频，再完成本目录手写循环。核验日课程 Notebook 在维护，不能把 Notebook 跑不通误认为自己没学会；代码以当前框架文档为准 |
| P1 | [Hugging Face Agents：Actions](https://huggingface.co/learn/agents-course/en/unit1/actions) | 用 JSON/code/function calling 和 stop-parse 解释模型文本如何成为外部动作 | 读完后画“生成动作→停止→解析→校验→执行→Observation”流程；不用安装 smolagents |

最重要的不是记住某家模型 API，而是理解：模型只能提出调用，程序负责验证、授权、执行和停止循环。

## 本地练习项目

完整代码位于 [tool-calling-practice](./tool-calling-practice/README.md)。它不依赖 Agent 框架，先用 fake model 验证运行时：

```powershell
cd 03-Function-Calling/tool-calling-practice
python -m pip install -e ".[dev]"
pytest
python -m tool_loop.demo
```

先读项目 README 的六层结构，再按 `runtime.py → registry.py → tools.py → guards.py → tests` 的顺序阅读代码。
