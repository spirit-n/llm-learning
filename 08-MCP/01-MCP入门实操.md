# 从第一个 MCP Server 到安全工具服务

## 1. 先画边界

```text
用户 → MCP Host（AI 应用）
          └─ MCP Client ←连接→ MCP Server → 业务 API/数据库
```

Host 负责用户体验与整体权限上下文；Client 管理协议连接；Server 暴露 tools/resources/prompts。数据库不是 MCP Server 本身，它是 Server 背后的系统。

## 2. 学习环境

在独立环境中按当前 [Python SDK](https://github.com/modelcontextprotocol/python-sdk) 安装，避免从旧视频固定版本：

```powershell
conda activate llm-learning
python -m pip install -U mcp
python -c "import mcp; print('MCP import OK')"
```

## 3. 第一个工具

先做无外部依赖的 `get_metric_definition`。输入只有指标名，输出结构化对象，未知指标返回明确错误码。用官方 inspector/测试客户端确认：初始化成功、工具可发现、schema 正确、调用成功、错误可解析。

再加入：

- Resource：指标口径文档或表结构，适合由客户端按需读取。
- Resource Template：如 `schema://{database}/{table}`。
- Prompt：只在确有复用价值时提供，不把安全规则只放 prompt。

### 按微软教程做 Inspector 验收

[Microsoft MCP Inspector 章节](https://github.com/microsoft/mcp-for-beginners/blob/main/03-GettingStarted/13-mcp-inspector/README.md) 把 Inspector 用作可视化测试客户端。第一次 Server 不连接 LLM，按以下顺序检查：

1. 能建立连接并读取 Server name/version。
2. 能列出 tools/resources/prompts。
3. Tool schema 的必填字段、类型和描述正确。
4. 合法参数返回结构化结果。
5. 缺字段、错类型、越界值返回受控错误。
6. Server 日志没有污染 stdio stdout。

Inspector 通过后再写自动化测试；图形界面不是测试替代品，但能帮助初学者看清协议对象。

## 4. stdio 与 Streamable HTTP

- stdio：Host 启动本地子进程，通过标准输入输出通信。适合本地工具；stdout 不能随意打印日志污染协议，日志写 stderr。
- Streamable HTTP：远程/集中服务，需处理认证、会话、网络错误、限流和部署。

先完成 stdio，再做 HTTP。遇到只讲旧 SSE transport 的教程，查当前规范迁移。

## 5. ClickHouse 工具分层

```text
输入 schema 校验
→ 用户/租户授权
→ SQL parser/AST 只读检查
→ 库表字段白名单
→ limit/timeout/扫描预算
→ 只读数据库账户执行
→ 结果截断/脱敏
→ 审计与结构化返回
```

每层都要单测。模型、MCP Client 或 Server 中任何一层被绕过时，数据库只读账户仍是最后防线。

配套工程把 Host 和 Server 的职责进一步拆开：`host.py` 只接受模型生成的业务参数，并从可信 `Principal` 注入 `tenant/request_id`；`server.py` 只负责协议注册；`service.py` 执行权限、幂等、Guard 和审计。不要把租户字段直接交给模型填写，也不要只因为 SDK 完成了 schema 校验就跳过业务授权。

运行边界测试：

```powershell
cd 08-MCP/mcp-practice
python -m pytest -q tests/test_host_boundary.py tests/test_query_service.py
```

## 6. 观测字段

记录 request/trace ID、server/tool/version、授权主体、参数摘要、耗时、结果行数、状态和错误码。不记录明文凭证；敏感 SQL/结果按策略脱敏。

## 7. 验收故障

主动测试 Server 崩溃、协议输出被日志污染、客户端取消、HTTP 断连、认证失效、工具超时、schema 改版、结果过大和恶意参数。每种情况都应有限失败，不让 Agent 无限重试。

微软课程的推荐主线已整理在 [Microsoft MCP for Beginners Python 导读](./02-微软MCP教程导读.md)，包含具体 Server、Client、stdio、HTTP、Testing、Auth 和 Inspector 链接。
