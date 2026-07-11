# LangChain 零基础入门与边界

LangChain 主要价值是统一模型、消息、工具和检索器接口，并提供常见 Agent 能力。它不会自动让系统可靠。

## 1. 安装策略

在 `llm-learning` 环境中按当前官方文档安装。框架变化快，不在笔记里锁死未来版本；项目实际开发时将已验证版本写入 `pyproject.toml`/lock file。

```powershell
conda activate llm-learning
python -m pip install -U langchain
python -c "import langchain; print(langchain.__version__)"
```

连接具体模型通常还需独立 integration 包。只安装你真正使用的 provider，不要照教程安装十几个 connector。

## 2. 学习顺序

1. Model + Messages：完成一次普通调用。
2. Structured Output：返回 Pydantic schema。
3. Tool：把普通 Python 函数声明为工具。
4. Agent：观察模型如何选择工具并循环。
5. Middleware：在调用前后注入权限、日志或限制。
6. Retriever：把自建 RAG 的检索接口接入。

## 3. 工具示意

```python
from langchain.tools import tool

@tool
def get_metric_definition(metric_name: str) -> str:
    """查询指标的正式定义；仅用于指标口径问题。"""
    definitions = {"success_rate": "成功数 / 请求数"}
    return definitions.get(metric_name, "NOT_FOUND")
```

工具描述影响模型选择，但返回 `NOT_FOUND` 后的业务行为仍需你设计。高风险工具在函数内部/调用中间件做权限与参数验证。

## 4. 为什么先手写再用框架

手写过 tool loop 后，你能识别 LangChain 负责的 schema 转换、消息循环和 integration，也能识别它没负责的授权、幂等、SQL 安全、验证和评测。否则容易把框架“能运行”误当成“可生产”。

## 5. 调试顺序

- 打印/trace 实际消息类型和工具 schema。
- 验证当前安装版本与文档版本匹配。
- 将真实模型换成 fake/stub，隔离业务循环。
- 将工具单独当普通函数测试。
- 检查 provider integration 是否正确序列化 tool call ID。

## 6. 不要照搬旧教程

遇到 `LLMChain`、旧 memory、旧 agent executor 或过时导入路径时，先查当前 [LangChain 文档](https://docs.langchain.com/oss/python/langchain/overview) 和 release/migration 说明。理解概念可以看旧视频，代码必须以当前版本验证。

## 7. 验收

- 同一业务工具能脱离 LangChain 单测。
- model/provider 能替换，业务 schema 不大改。
- 能展示一次工具 schema 错误、一次超时和一次权限拒绝的 trace。
- 能说出哪些可靠性问题不属于 LangChain 自动解决范围。
