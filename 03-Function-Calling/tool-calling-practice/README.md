# 受控 Tool Calling 练习项目

这个项目不依赖 LangChain。目标是先看清楚模型与运行时的职责边界：

```text
fake model 提议工具调用
→ Registry 查找工具
→ Pydantic 校验参数
→ 权限与 SQL Guard 校验
→ timeout 内执行
→ 脱敏并截断结果
→ tool message 返回模型
→ 最终答案或继续循环
```

模型只能提出调用，不能绕过 Registry、权限、SQL Guard 或工具超时。

## 运行

```powershell
cd 03-Function-Calling/tool-calling-practice
python -m pip install -e ".[dev]"
pytest
tool-loop-demo
```

也可以不用命令行入口：

```powershell
python -m tool_loop.demo
```

## 三个内置工具

- `get_metric_definition(metric_name)`：读取固定指标口径。
- `describe_table(table)`：返回裁剪后的表结构，不暴露敏感列。
- `run_readonly_sql(sql, max_rows)`：使用 SQL AST 校验、表/列白名单、强制 `LIMIT` 和 SQLite `query_only` 双重保护。

## 六层结构

| 层          | 文件                      | 作用                                 |
| ----------- | ------------------------- | ------------------------------------ |
| Tool Schema | `models.py`、`tools.py`   | 定义参数和返回契约                   |
| 选择/路由   | `fake_model.py`           | fake model 提出调用，便于稳定测试    |
| 消息处理    | `runtime.py`              | 维护 call ID 和 tool message         |
| 集成层      | `registry.py`、`tools.py` | 注册并执行普通 Python 工具           |
| 错误与验证  | `guards.py`、`runtime.py` | 参数、权限、SQL、timeout、脱敏、截断 |
| 状态管理    | `runtime.py`              | 最大步数、重复调用、审计记录         |

## 测试覆盖

- 合法工具调用与真实只读 SQL 查询
- 未知工具
- 参数缺失
- 权限拒绝
- `DROP`、多语句、敏感列和 `SELECT *`
- 工具 timeout
- 重复调用停止
- 超长结果截断和敏感字段脱敏
- 达到最大步骤退出

`RunResult.audit_log` 提供工具选择、执行结果、无效调用次数和耗时，可继续扩展为评测指标。

## 学习版与生产版的边界

本项目用线程实现通用工具 timeout。超时后运行时会立刻返回受控错误，但 Python 线程无法强制终止已经开始的阻塞函数。生产环境还应使用数据库 statement timeout、HTTP 客户端 timeout、可取消任务或隔离进程，并补充并发和成本限额。

## 真实模型实验

`tests_live/test_live_tool_runtime.py` 把真实模型适配到手写的 `ToolRuntime`，验证模型提出的调用仍会经过 Registry、参数校验、权限和审计。配置方式见 [统一 live 配置](../../shared/README.md)，运行 `python -m pytest -q tests_live -m live`。普通 `pytest` 仍只运行离线用例。
