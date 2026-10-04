# 08｜Model Context Protocol（MCP）

版本必读：[2026-10 协议与 SDK 迁移边界](./03-2026协议迁移边界.md)。当前工程保留 `mcp>=1.29,<2` 学习基线；文中的 initialize/session 流程属于旧协议，不能当作 2026-07-28 的通用流程。

**安排：** 第 6 周前 3 天，P0。

详细学习：[从第一个 MCP Server 到安全工具服务](./01-MCP入门实操.md)。

微软完整课程导读：[Microsoft MCP for Beginners 的 Python 学习路线](./02-微软MCP教程导读.md)。

配套工程：[mcp-practice](./mcp-practice/README.md)。工程用 FastMCP 实现 Tool、Resource、Resource Template、Prompt、stdio 客户端和 Streamable HTTP；Host 侧补充能力 allowlist、可信身份参数注入、scope、schema 预检和错误分类，服务侧用 SQL AST Guard、幂等冲突检测与脱敏审计覆盖主要攻击/误用场景。

快速开始：

```powershell
cd 08-MCP/mcp-practice
python -m pip install -e ".[dev]"
python -m mcp_lab.demo
python -m mcp_lab.client
python -m pytest -q
```

## 零基础前置

先看 [基础术语表](../00-学习规划/基础术语表.md) 中 Client/Server、HTTP、JSON、API 和 Tool。会写一个 Python 函数并理解参数/返回值即可开始；数据库与认证可在最小 Server 跑通后再补。

## 先分清三层

- Function Calling：某个模型 API 如何表达“我要调用工具”。
- MCP：Host/Client 如何发现并调用外部 Server 提供的工具、资源和提示。
- Harness：谁做权限、执行、验证、恢复、审计和成本控制。

MCP 标准化连接，不会自动解决工具安全、业务权限和结果正确性。

## 核心概念

- Host、Client、Server 以及连接生命周期。
- tools、resources、resource templates、prompts。
- 能力协商、初始化、通知与错误。
- stdio 与 Streamable HTTP；旧 SSE 内容只用于理解历史。
- 本地进程、远程服务、认证授权和信任边界。

## ClickHouse MCP Server

```text
list_databases()
list_tables(database)
describe_table(database, table)
get_metric_definition(metric_name)
explain_sql(sql)
run_readonly_sql(sql, max_rows)
```

安全要求：只允许 SELECT、单语句、库表白名单、字段级脱敏、自动/强制 limit、查询超时、扫描量限制、用户到数据库权限映射、完整审计、错误信息去敏。解析 SQL 时优先使用 parser/AST，不依靠字符串 `startswith("select")`。

## 验收

- Server 能分别通过 stdio 与 HTTP 被测试客户端发现和调用。
- 工具 schema 清晰，错误可操作但不泄露内部信息。
- 10 个攻击/误用案例被测试：注释绕过、多语句、子查询写入、危险函数、超大查询、越权表、敏感列、超时、断连、重复调用。
- 能解释 MCP 与 REST：MCP 为 Agent 发现与交互提供通用语义；底层业务仍可由 REST/DB 等实现。

## 资料怎么用

| 阶段/优先级 | 资料 | 它是干什么的 | 零基础怎么使用 |
|---|---|---|---|
| 建立直觉/P1 | [B站 MCP 教程](https://www.bilibili.com/video/BV17dawzvEx5/) | 中文介绍 Host/Client/Server、传输方式和 FastMCP 实战 | 第一遍只画组件图；视频可能包含旧 SSE 内容，涉及传输/API 时回当前官方文档核对 |
| P0 | [MCP Architecture](https://modelcontextprotocol.io/docs/learn/architecture) | 官方用图解释 Host、Client、Server 如何连接，以及 tools/resources/prompts 的职责 | 先读这页再写代码。读完应能用“插座/协议”类比解释 MCP，但也要知道安全和业务权限不由协议自动完成 |
| 查规则/P2 | [MCP Specification](https://modelcontextprotocol.io/specification/) | 协议的正式规范，包含生命周期、消息、能力协商和传输要求 | 它像法律条文，不适合第一遍通读。实现遇到初始化、错误码、transport 或兼容问题时查对应章节 |
| P0 | [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk) | 官方 Python 实现、安装命令和 Server/Client 示例 | 先运行最小无依赖工具，再加数据库。始终看当前 README 与 examples，不从旧博客复制固定版本代码 |
| P0/P1 | [Microsoft MCP for Beginners（简体中文入口）](https://github.com/microsoft/mcp-for-beginners/blob/main/translations/zh-CN/README.md) | 微软的跨语言完整课程，覆盖概念、安全、Server/Client、stdio/HTTP、测试、认证、Inspector、部署与实践 | 只走 Python 主线，按本目录导读完成 P0 章节；其他语言、Azure、多模态和社区内容后选 |

学习顺序必须是：架构图 → 无副作用工具 → stdio → 测试客户端 → 安全 Guard → HTTP。不要第一天就连接真实数据库。
