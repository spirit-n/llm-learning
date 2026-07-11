# 微软三套 Beginner 教程总导读

核验日期：2026-07-11。三个仓库都在持续更新，章节链接和代码运行方式以仓库当前 README 为准。

## 三套教程分别解决什么

| 教程 | 主要回答的问题 | 在本计划中的位置 | 使用方式 |
|---|---|---|---|
| [Microsoft LangChain for Beginners](https://github.com/microsoft/langchain-for-beginners) | 如何用 LangChain 连接模型、消息、结构化输出、工具、Agent、MCP 与 RAG | 第 1～6 周，重点对应 `02`～`06`、`08` | P0/P1：读章节、运行选定 Python 示例、改造成自己的指标场景 |
| [Microsoft AI Agents for Beginners](https://github.com/microsoft/ai-agents-for-beginners) | Agent 有哪些设计模式，如何使用工具、规划、多 Agent、记忆、协议、安全与生产化 | 第 4～8 周，对应 `06`～`15` | 概念主线；代码主线偏 Microsoft Agent Framework/Foundry，不强制全部运行 |
| [Microsoft MCP for Beginners](https://github.com/microsoft/mcp-for-beginners) | MCP 的概念、安全、Server/Client、stdio/HTTP、测试、认证、部署与高级能力 | 第 6～7 周，对应 `08`、`12`、`15` | P0：只选 Python 路线，完成 Server/Client/Inspector/安全测试 |

## 为什么不按三个仓库从头到尾连续学

内容有大量重叠。例如 LangChain 课程也讲 Tool、Agent、MCP 与 RAG；AI Agents 课程也讲 Tool、Agentic RAG、MCP、Context 和生产；MCP 课程又单独深入安全与部署。

若依次完整通读，会重复看概念，却很晚才做自己的项目。本计划采用“按能力汇合”：

```text
第 1 周：LangChain 课程 0～4
第 2～3 周：LangChain 课程 7 + 自建 RAG
第 4 周：LangChain 课程 5 + AI Agents 1～4、7
第 5 周：LangChain 课程 8 + AI Agents 5、8、12、13
第 6 周：LangChain 课程 6 + MCP 课程 0～3 + AI Agents 11、18
第 7 周：MCP 课程测试/认证/部署 + AI Agents 6、10
第 8 周：AI Agents 其余选修 + 项目和面试
```

## 零基础统一学习动作

每个微软章节都用同一套方法：

1. 先读 README，只写一张数据流图。
2. 用 5 句话回答：输入、输出、核心对象、失败点、为什么需要它。
3. 运行最小示例；若依赖 Azure/付费资源，先用 fake model 或只做概念练习。
4. 把示例里的天气/旅行/客服场景改成指标口径、SQL 或企业文档场景。
5. 故意触发一个失败并写复盘。
6. 最后才看 solution，不能第一步复制答案。

## 不要混用依赖环境

三套课程更新速度不同，依赖可能互相冲突。不要把三个仓库的 `requirements.txt` 全装进 `llm-learning` 环境。需要运行某仓库时单独创建环境：

```powershell
conda create -n ms-langchain-course python=3.11 -y
conda create -n ms-agent-course python=3.11 -y
conda create -n ms-mcp-course python=3.11 -y
```

一次只激活一个：

```powershell
conda activate ms-langchain-course
python --version
where python
```

Python `3.11` 只是兼容性较广的学习示例；若仓库当前 setup 指定其他版本，应以仓库要求为准。

## GitHub 怎么看，不要求先学 Git

- 浏览器打开根仓库：先看 README 目录。
- 点击章节文件夹，再读里面的 `README.md`、assignment 和 code。
- `code` 是示例，`solution` 是参考答案；先自己做。
- 查看文件更新时间，旧代码与当前官方 API 不一致时，以官方 docs 为准。
- 简体中文翻译方便理解，但仓库也提醒机器翻译可能不准确；关键参数和安全规则回英文原文核对。

## 总验收

三套课程不是三个简历项目。真正的作品仍是本仓库规划的 RAG、指标 Agent 与 MCP Server。微软课程负责提供结构化教材和练习，你要把知识合并进自己的项目并给出评测证据。
