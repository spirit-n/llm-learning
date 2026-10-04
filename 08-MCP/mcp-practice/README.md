# 安全 MCP Host/Server 与协议边界练习

2026-10 说明：此工程是 **Python SDK 1.x / 2025 协议基线**，不是最新版示例；安装命令需保留 `<2`。新协议的无握手请求、MRTR、Tasks 扩展和远程鉴权参见 [迁移边界](../03-2026协议迁移边界.md)。这里的 HTTP token/SSRF 测试不等于完整 OAuth 互操作验证，也不宣称支持 Tasks/Elicitation 全流程。

项目使用当前官方 Python SDK 的 `FastMCP` 和 `ClientSession`，实现一个不连接真实数据库的指标服务。除 Tool、Resource、Resource Template 和 Prompt 外，还实现了 Host 侧能力 allowlist、可信参数注入、scope 授权、参数预检、超时和分层错误，并把查询权限、幂等与审计下沉到不依赖 MCP 的服务层。

默认 demo 和单元测试离线运行；`tests_live/` 只让真实模型选择 MCP Tool，Server 工具仍使用固定教学数据。

## 架构与信任边界

```text
模型输出 tool name + 业务参数（不可信）
  → SafeMCPHost
      ├─ 只暴露 allowlist 中已发现的能力
      ├─ 校验 scope 与 JSON Schema
      ├─ 注入认证网关签发的 auth_context / request_id
      └─ 统一 timeout、传输错误和工具错误
  → MCP transport（进程内 / stdio / Streamable HTTP）
  → FastMCP adapter（验签 + scope 复核）
  → SchemaService / QueryService（再次授权、投影、SQL Guard、幂等、审计）
  → fake ClickHouse
```

关键原则：模型可以填写 `sql`、`metric_name`、`max_rows` 等业务参数，但客户端提交 `tenant="tenant-a"` 不构成认证。认证网关先把 `actor_id/tenant/scopes/exp` 签成短期 `auth_context`；`SafeMCPHost` 隐藏并注入它，FastMCP Server 验签和检查 scope，Service 再独立复核 tenant/scope。伪造、篡改或缺少上下文都不能到达查询执行。

能力目录提供给模型前会删除 `auth_context/request_id` 的 schema 字段，但 Host 内部保留 Server 原始 schema，注入可信值后再校验。无认证 Resource 只暴露 public schema：带敏感列的表返回 `TABLE_NOT_PUBLIC`；授权 `describe_table` 也只返回非敏感列和被隐藏列数量，不泄露敏感列名。

本地 demo 使用进程内随机签名密钥。分离 stdio/HTTP 进程时应由部署环境设置至少 32 bytes 的 `MCP_AUTH_SECRET`，并由上游认证网关签发 token；普通模型进程不应持有该签名密钥。测试包含真实 stdio 子进程的验签调用，transport 改成 Streamable HTTP 时复用同一 Server/Service 边界。

## 运行

```powershell
cd 08-MCP/mcp-practice
python -m pip install -e ".[dev]"
python -m mcp_lab.demo
python -m mcp_lab.client
python -m pytest -q
```

启动 HTTP Server：

```powershell
python -m mcp_lab.server --transport streamable-http --port 8000
```

另开终端测试 HTTP Client：

```powershell
python -m mcp_lab.client --transport streamable-http --url http://127.0.0.1:8000/mcp
```

## 建议阅读顺序

1. `models.py`、`auth.py`：协议稳定输出、可信身份与短期签名上下文。
2. `domain.py`：不依赖 MCP 的指标、schema 和固定数据。
3. `guard.py`：AST 解析、只读限制、表/列权限、危险函数和强制 LIMIT。
4. `service.py`：scope 校验、字段投影、幂等冲突和脱敏审计。
5. `server.py`：Tool、Resource、Resource Template、Prompt 如何注册成协议能力。
6. `host.py`：能力发现、allowlist、可信参数注入、schema 预检、超时和错误分类。
7. `client.py`：真实 stdio/HTTP 会话的初始化、能力协商与调用。
8. `demo.py`：不启动子进程也能观察完整 Host → MCP → Service 链路。
9. `tests/test_host_boundary.py`：逐个看权限、参数污染、超时、传输错误和工具错误。
10. `tests/test_guard.py`、`test_query_service.py`：看攻击输入、最小结果集和幂等冲突。

## 错误分类

| 类别 | 例子 | 默认是否可重试 |
|---|---|---|
| `policy_error` | 未发现工具、缺 scope、缺认证上下文、模型覆盖可信字段 | 否 |
| `protocol_error` | 参数不符合 schema、断连、timeout | 仅瞬时传输/timeout 可有限重试 |
| `tool_error` | 越权表、SQL Guard 拒绝、幂等冲突 | 否，先修改请求 |
| `success` | structured content 中 `ok=true` | 不适用 |

“HTTP 200/MCP call 成功”不等于业务成功，Host 仍要读取结构化结果中的 `ok/error`。

真实生产环境还必须使用只读数据库账户、认证、超时/扫描预算、限流、脱敏日志和持久化审计。本项目的 Guard 是学习基线，不是数据库最后防线。

## 推荐实验

1. 让模型参数包含 `auth_context="forged"`，观察 Host 在进入 transport 前拒绝；再绕过 Host 直调 Server，观察验签仍拒绝。
2. 使用同一 `request_id` 调两条不同 SQL，观察 `IDEMPOTENCY_CONFLICT`。
3. 在 FakeTransport 中增加延迟或抛出连接异常，比较 `protocol_error` 与 SQL Guard 的 `tool_error`。
4. 修改任一工具 schema 后用 `catalog.fingerprint` 检测能力漂移，再决定 Host 是否兼容。
5. 最后才把 `LocalFastMCPTransport` 换成 stdio/HTTP ClientSession；业务服务和安全策略不应随 transport 重写。

## 真实模型实验

`tests_live/test_live_mcp_host.py` 让真实模型充当 Host：读取 MCP Tool schema、选择工具、调用 FastMCP Server，再根据结构化结果回答。配置方式见 [统一 live 配置](../../shared/README.md)，运行 `python -m pytest -q tests_live -m live`。
