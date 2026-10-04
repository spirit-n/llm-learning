# Microsoft MCP for Beginners 的 Python 学习路线

- 主仓库：[microsoft/mcp-for-beginners](https://github.com/microsoft/mcp-for-beginners)
- [简体中文入口](https://github.com/microsoft/mcp-for-beginners/blob/main/translations/zh-CN/README.md)

这套教程同时提供 .NET、Java、TypeScript/JavaScript、Rust 和 Python 示例。你有 Java 背景，但 8 周求职主线仍只运行 Python；Java 示例只用于比较 Spring AI/类型系统，不要同时维护两套实现。

## 版本提示（2026-10-04 更新）

早期笔记将 `2026-07-28` 记作候选规范；该日期已过去，不能再用“尚未发布”描述。新版已发生协议和 SDK 层面的破坏性变化，见 [版本迁移边界](./03-2026协议迁移边界.md)。本仓库主动保留旧版练习基线：

- 当前工程使用 Python SDK 1.x / 2025 协议流程，安装保留 `<2`。
- 2026-07-28 新协议先理解差异；需要迁移时在独立环境完成互操作测试。
- 外部教程可能已切到 v2；不要将其最新代码直接拷进 v1 练习。

## Python 环境

为课程单建环境：

```powershell
conda create -n ms-mcp-course python=3.11 -y
conda activate ms-mcp-course
python -m pip install "mcp[cli]>=1.29,<2"
python -c "import mcp; print('MCP SDK OK')"
```

浏览课程不必先 clone。真正运行 Python 示例时再下载：

```powershell
git clone https://github.com/microsoft/mcp-for-beginners.git
cd mcp-for-beginners
```

每个子章节可能还有自己的依赖/命令，进入章节后以当前 README 为准。不要在根目录盲目安装所有语言依赖。

## 第一阶段：P0 主线（第 6 周，约 12～16 小时）

| 顺序 | 教程 | 学什么 | 你的验收 |
|---:|---|---|---|
| 1 | [00 Introduction](https://github.com/microsoft/mcp-for-beginners/tree/main/00-Introduction) | MCP 为什么出现、标准化 Agent/工具连接 | 能画 Host→Client→Server→业务系统，区分 MCP 与模型 |
| 2 | [01 Core Concepts](https://github.com/microsoft/mcp-for-beginners/tree/main/01-CoreConcepts) | tools、resources、prompts、生命周期和消息 | 为“指标定义、表 schema、SQL 查询”选择正确 primitive 并解释 |
| 3 | [02 Security](https://github.com/microsoft/mcp-for-beginners/tree/main/02-Security) | 威胁、信任边界、认证授权、输入输出风险 | 建 10 个攻击用例；明确协议安全不等于业务权限 |
| 4 | [03 Getting Started 总览](https://github.com/microsoft/mcp-for-beginners/tree/main/03-GettingStarted) | 多语言环境、Server/Client、测试和集成地图 | 只选 Python 子章节，列出本周完成顺序 |
| 5 | [3.1 First Server](https://github.com/microsoft/mcp-for-beginners/blob/main/03-GettingStarted/01-first-server/README.md) | 用 FastMCP 创建最小 Server 与 Tool | 先做 `add`/`get_metric_definition`，无数据库、可独立测试 |
| 6 | [3.2 First Client](https://github.com/microsoft/mcp-for-beginners/blob/main/03-GettingStarted/02-client/README.md) | Client 连接、发现和调用 Server | 打印工具列表、schema、调用结果和错误；理解 Client 与 Host 区别 |
| 7 | [3.5 stdio Server](https://github.com/microsoft/mcp-for-beginners/blob/main/03-GettingStarted/05-stdio-server/README.md) | 本地子进程与标准输入输出传输 | stdout 不打印日志；日志走 stderr；Host 能稳定启动/关闭子进程 |
| 8 | [3.8 Testing](https://github.com/microsoft/mcp-for-beginners/blob/main/03-GettingStarted/08-testing/README.md) | Server/Client 测试与错误验证 | 测 schema 错、未知工具、timeout、Server 崩溃和重复调用 |
| 9 | [3.13 MCP Inspector](https://github.com/microsoft/mcp-for-beginners/blob/main/03-GettingStarted/13-mcp-inspector/README.md) | 可视化发现/调用 tools、resources、prompts | 截图/记录 capabilities、合法调用和非法参数结果 |
| 10 | [3.6 HTTP Streaming](https://github.com/microsoft/mcp-for-beginners/blob/main/03-GettingStarted/06-http-streaming/README.md) | 远程 HTTP 连接与流式交互 | stdio 稳定后再做；测试断连、取消、超时和并发 |
| 11 | [3.11 Simple Auth/RBAC](https://github.com/microsoft/mcp-for-beginners/blob/main/03-GettingStarted/11-simple-auth/README.md) | 基础认证、角色权限 | 用户身份传到工具授权；无权表在执行前拒绝并审计 |

## 第二阶段：P1 工程化（第 7 周，约 6～10 小时）

| 模块 | 用途 | 取舍 |
|---|---|---|
| [04 Practical Implementation](https://github.com/microsoft/mcp-for-beginners/tree/main/04-PracticalImplementation) | SDK、调试、测试、可复用实现和分页等 | 挑与你的 ClickHouse Server 相关内容，重点分页/大结果、错误和测试 |
| [08 Best Practices](https://github.com/microsoft/mcp-for-beginners/tree/main/08-BestPractices) | 生产设计与通用实践 | 转成代码审查清单，不只阅读 |
| [12 Tooling](https://github.com/microsoft/mcp-for-beginners/tree/main/12-tooling) | MCP 开发、调试和生态工具 | 只装当前项目需要的工具，记录版本与来源 |
| [11 Hands-on Labs](https://github.com/microsoft/mcp-for-beginners/tree/main/11-MCPServerHandsOnLabs) | 多个生产化实验，包含数据库集成路线 | 原课程含 PostgreSQL 路线；选择测试/认证/部署思想迁移到 ClickHouse，不必完整照做 13 个实验 |

## 第三阶段：P2/P3 选修

| 模块 | 为什么后学 |
|---|---|
| [05 Advanced Topics](https://github.com/microsoft/mcp-for-beginners/tree/main/05-AdvancedTopics) | 多模态、Azure、OAuth、routing、scaling 等面较广；先有可运行 Server 才有上下文 |
| [06 Community Contributions](https://github.com/microsoft/mcp-for-beginners/tree/main/06-CommunityContributions) | 学开源贡献和社区案例，不是求职核心实现 |
| [07 Lessons from Early Adoption](https://github.com/microsoft/mcp-for-beginners/tree/main/07-LessonsfromEarlyAdoption) | 真实采用经验有价值，但应在做过项目后阅读才能判断 |
| [09 Case Study](https://github.com/microsoft/mcp-for-beginners/tree/main/09-CaseStudy) | 案例用于系统设计复盘，不替代自己的可测项目 |
| [10 AI Toolkit](https://github.com/microsoft/mcp-for-beginners/tree/main/10-StreamliningAIWorkflowsBuildingAnMCPServerWithAIToolkit) | 偏具体工具链；岗位使用微软开发工具时再深入 |
| `1.1 2026-07-28 RC` | 截至核验日仍是未来候选变化，只做技术雷达并等待正式发布/SDK 支持 |

## 把计算器示例升级成求职项目

按四次迭代，不要直接连真实生产库：

1. `calculator`：只验证 SDK、stdio、Client、Inspector。
2. `metric_catalog`：用本地 JSON 提供指标定义和 fake schema。
3. `fake_clickhouse`：模拟 SQL 执行，完成 Guard、timeout、结果截断和测试。
4. `readonly_clickhouse`：只读测试库、最小权限账户、表/列白名单、limit、审计。

每一步都能独立运行和回退，出现问题时才知道是协议、工具、数据库还是模型层。

## 必须会解释的 10 个问题

1. Host、Client、Server 各是谁？
2. Tool、Resource、Prompt 什么时候用？
3. stdio 为什么不能向 stdout 随便打印日志？
4. stdio 与 Streamable HTTP 如何选？
5. MCP 与 Function Calling、REST 的关系？
6. 工具 schema 正确为什么仍可能越权？
7. Client 断连/取消时 Server 怎么办？
8. 大结果如何分页、截断和保留可追踪引用？
9. Server/Tool 版本变化如何兼容和测试？
10. 为什么数据库账户本身仍必须只读和最小权限？
