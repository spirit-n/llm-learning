# 01｜Python 工程基础

**安排：** 第 1 周前 2 天，P0。目标是能写 LLM 应用，不是系统重学计算机基础。

## 零基础阅读顺序

1. [Windows 环境安装：Anaconda、VS Code 与验证](./01-Windows环境安装.md)
2. [Python 零基础语法](./02-Python零基础语法.md)
3. [Jupyter、Notebook 与 ipykernel](./03-Jupyter与ipykernel.md)
4. 打开并运行 [Python 入门实验 Notebook](./python入门实验.ipynb)
5. 完成 [练习与验收](./04-练习与验收.md)

## 从 Java 迁移时重点掌握

| Java 经验 | Python 对应点 | 易错点 |
|---|---|---|
| Maven/Gradle | conda 环境 + pip/`uv` + `pyproject.toml` | 不要全局安装依赖或把包全装进 base |
| POJO/Jackson | Pydantic `BaseModel` | 运行时校验与普通 type hint 不同 |
| CompletableFuture | `asyncio`、`async/await` | CPU 阻塞和同步 SDK 会卡事件循环 |
| SLF4J | `logging`/结构化日志 | 不打印密钥、完整 prompt 和敏感数据 |
| JUnit | pytest | fixture、parametrize、mock 边界 |
| Spring Boot | FastAPI | 依赖注入更轻量，生命周期管理不同 |

## 必学清单

- 基础：类型、列表/字典/集合、推导式、函数、类、异常、上下文管理器。
- 工程：包、模块、虚拟环境、`pyproject.toml`、环境变量、配置分层。
- 数据：Pydantic schema、JSON 序列化、泛型和 `Protocol` 基础。
- I/O：文件、HTTP、异步、timeout、retry、并发限制。
- 质量：日志、pytest、lint/format、类型检查。

## 最小练习

1. 为聊天请求定义 Pydantic 模型：`messages`、`model`、`temperature`。
2. 写一个异步 LLM client interface，并提供 fake client 用于测试。
3. FastAPI 暴露 `/health`、`/chat`，统一错误响应。
4. 记录 request ID、模型、耗时、token、状态；敏感内容脱敏。
5. 测试成功、超时、限流、无效 JSON、上游 5xx 五类情况。

## 面试必须能讲

- `async` 为什么不等于“自动并行”？
- type hint 和 Pydantic 运行时校验有什么区别？
- 为什么 LLM 调用必须设置 timeout、retry 和并发上限？
- Java 后端能力如何迁移到 Python AI 应用工程？

## 资料怎么用

这些链接不是让你现在从头读到尾。官方文档更像字典：先完成中文教程和练习，遇到具体问题再查对应页面。

| 优先级 | 资料 | 它是干什么的 | 零基础怎么使用 |
|---|---|---|---|
| P0 | [Python Tutorial](https://docs.python.org/3/tutorial/) | Python 官方语法教程，解释变量、容器、控制流、函数、模块、异常、类等语言基础 | 先读本目录中文教程；第 1 周只查第 3～5 章。看不懂英文可用浏览器翻译，不要试图一次读完 |
| P2 | [uv 文档](https://docs.astral.sh/uv/) | 更快的 Python 包和项目管理工具，可替代部分 `pip`、`venv` 工作 | 目前先用 conda，不必安装。等能独立创建环境、安装包后，再看 Getting Started，理解它解决“依赖安装和锁版本”问题 |
| P0 | [FastAPI 文档](https://fastapi.tiangolo.com/) | 用 Python 编写 HTTP 后端接口；后面会把 LLM、RAG 和 Agent 暴露为 API | 第 1 周先看 First Steps，照着做 `/health` 接口；依赖注入、认证、部署稍后再看 |
| P0 | [Pydantic 文档](https://docs.pydantic.dev/latest/) | 把外部 JSON 转成可靠的 Python 对象，并检查字段类型、长度和范围 | 先看 Models 与 Fields。目标是会定义 `BaseModel`，能看懂 `ValidationError`，不用研究全部高级类型 |
| P1 | [pytest 文档](https://docs.pytest.org/) | 自动运行测试，防止代码修改后旧功能悄悄坏掉 | 先看 Get Started，学会 `assert`、测试文件命名和运行 `python -m pytest`；fixture/mocking 在项目中遇到再学 |
| P1 | [Microsoft Python for Beginners](https://github.com/microsoft/c9-python-getting-started/tree/master/python-for-beginners) | 微软的零基础 Python 课程资料，可补变量、条件、循环、函数和调试 | 先完成本仓库 Notebook；只选不会的主题，不需要把较旧课程从头通刷 |

如果只完成 P0，你已经能进入 LLM API 和 RAG；P1/P2 可以随着项目补充。
