# 大模型应用与 Agent 工程：8 周求职倒排学习计划

这是一套面向有 Java/后端经验、准备转向 **AI 应用工程师、Agent 工程师、RAG 工程师、LLM 后端工程师** 的学习仓库。目标不是把所有框架学完，而是在 8 周内形成可展示、可运行、可讲清楚的作品与面试能力。

> 建议投入：每周 20～30 小时。全部主题都会保留，通过 P0～P3 标记求职优先级；优先级低表示可以后做，不表示删除。

## 8 周后应交付什么

- 一个支持混合检索、重排、引用和评测的企业知识库 RAG。
- 一个带 SQL Guard、失败修复、trace 的指标查询 Agent。
- 一个只读 ClickHouse MCP Server，并能被 Agent 调用。
- 30～50 条 golden set、一次可复现的评测报告和一份失败案例复盘。
- 项目 README、架构图、演示视频、简历项目描述和面试题答案。

## 零基础第一次打开，请按这里开始

1. 不要急着安装 LangChain。先打开 [Windows 环境安装](./01-Python工程基础/01-Windows环境安装.md)。
2. 安装 Anaconda、创建 `llm-learning` 环境、安装 Jupyter/ipykernel，并完成文末自检。
3. 阅读 [Python 零基础语法](./01-Python工程基础/02-Python零基础语法.md)。
4. 阅读 [Jupyter 与 ipykernel](./01-Python工程基础/03-Jupyter与ipykernel.md)。
5. 在 VS Code 中运行 [Python 入门实验 Notebook](./01-Python工程基础/python入门实验.ipynb)。
6. Notebook 能 `Restart Kernel and Run All` 后，再进入第 1 周 LLM 内容。

每个主题目录的 `README.md` 是地图，其余编号文件才是详细教程。先按编号读，不必一次读完整个仓库。

如果你不是计算机科班，建议环境安装前先读：

- [非科班零基础学习方法](./00-学习规划/零基础学习方法.md)：终端、命令、报错、英文文档应该怎么学。
- [大模型应用基础术语表](./00-学习规划/基础术语表.md)：解释环境、包、API、HTTP、JSON、数据库、向量、模型、Agent 等常见名词。
- [微软三套 Beginner 教程总导读](./00-学习规划/微软Beginner教程总导读.md)：把 LangChain、AI Agents、MCP 三套课程映射到 8 周计划。
- [章节配套教程索引](./00-学习规划/章节配套教程索引.md)：为 Python、RAG、Agent、Context、评测、部署等每章筛选主教程与补充教程。

## 学习顺序

| 周次 | 主线 | 当周可验收结果 | 求职动作 |
|---|---|---|---|
| 第 1 周 | Python、LLM API、Prompt、结构化输出、Function Calling | FastAPI LLM 服务 + 3 个工具 | 建岗位表，收集 30 个 JD |
| 第 2 周 | RAG 基线：解析、chunk、embedding、向量检索、引用 | 可回答自有文档的 Naive RAG | 从 JD 提取技能关键词 |
| 第 3 周 | RAG 进阶、RAGAS、Transformer 概念卡 | 对照实验与评测报告 v1 | 写项目一简历草稿 |
| 第 4 周 | LangChain、LangGraph、HITL、微调概念卡 | LangGraph 版指标查询 Agent | 开始小批量投递与复盘 |
| 第 5 周 | AgentScope 框架对照、Context、Skills、Docker 基础 | Context Builder + Skill + 容器化 `/health` | 每周投递 15～25 个匹配岗位 |
| 第 6 周 | MCP、Harness、安全；A2A 概念 | ClickHouse MCP + Agent Harness | 第一次模拟面试 |
| 第 7 周 | 评测、trace、部署、鉴权、成本与监控 | Docker 化服务 + eval 报告 v2 | 集中投递、修订简历 |
| 第 8 周 | 项目打磨、Transformer/微调面试表达、系统设计 | 作品集 + 演示 + 面试答案 | 每天投递、模拟面试、复盘 |

完整的每日安排见 [00-学习规划/8周倒排计划.md](./00-学习规划/8周倒排计划.md)。

## 目录

- [00-学习规划](./00-学习规划/README.md)：使用方法、周计划、能力矩阵、资源导航
- [01-Python工程基础](./01-Python工程基础/README.md)
- [02-LLM与Prompt](./02-LLM与Prompt/README.md)
- [03-Function-Calling](./03-Function-Calling/README.md)
- [04-RAG检索工程](./04-RAG检索工程/README.md)
- [05-LangChain](./05-LangChain/README.md)
- [06-LangGraph](./06-LangGraph/README.md)
- [07-AgentScope](./07-AgentScope/README.md)
- [08-MCP](./08-MCP/README.md)
- [09-A2A](./09-A2A/README.md)
- [10-Context-Engineering](./10-Context-Engineering/README.md)
- [11-Agent-Skills](./11-Agent-Skills/README.md)
- [12-Harness-Engineering](./12-Harness-Engineering/README.md)
- [13-评测与可观测性](./13-评测与可观测性/README.md)
- [14-模型基础与微调](./14-模型基础与微调/README.md)
- [15-部署与生产工程](./15-部署与生产工程/README.md)
- [16-综合项目](./16-综合项目/README.md)
- [17-面试与求职](./17-面试与求职/README.md)
- [18-前沿技术雷达](./18-前沿技术雷达/README.md)

## 学习纪律

1. 每学一个概念，必须回答：它解决什么问题？不用它会怎样？替代方案是什么？
2. 代码以“能验证设计”为目标，不抄大型模板；每周至少写一次失败复盘。
3. 框架 API 变化快，先读当前官方文档；视频用于建立直觉，不作为 API 真相来源。
4. 从第 4 周开始投递，不等“全部学完”。面试反馈反向决定下一周补什么。
5. 所有项目都记录版本、配置、数据集、指标、失败类型和成本，保证可复现。

## 优先级说明

- **P0 求职核心**：必须独立实现，能排错，能用数据解释取舍。
- **P1 工程重要**：至少完成一个实验，能接入综合项目。
- **P2 岗位相关**：能讲清原理；遇到相关 JD 时补齐实战。
- **P3 技术雷达**：理解解决的问题、成熟度和风险，保持更新。
