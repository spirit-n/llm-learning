# MySQL 持久化存储

四个练习统一使用 `learning-database` 配置层。正常运行读取 `DATABASE_URL`，不再自动创建 SQLite 文件；只有显式传入 SQLite 路径的离线测试仍使用 SQLite。

## 已部署的数据库

- 地址：`192.168.11.8:3306`，MySQL **8.4.12**。
- Docker 容器：`mysql84`，开机启动 Docker，容器 `restart=unless-stopped`。
- 数据目录：宿主机 `/home/mysql84/data` → 容器 `/var/lib/mysql`。
- 账号：`root`，密码沿用已有配置，只保存于被 Git 忽略的仓库根 `.env` 和服务器 `/home/mysql84/mysql.env`（权限 600）。
- 默认数据库：`llm_learning`，InnoDB、utf8mb4；`innodb_flush_log_at_trx_commit=1`、`sync_binlog=1`。
- 原 `mysql57` 容器已删除，没有迁移旧业务数据；旧绑定目录不供新实例使用。
- 可复现部署配置：[compose.yaml](../../infra/mysql/compose.yaml)。先将配置复制到服务器，再运行 `docker compose -f compose.yaml up -d`；不要让两个部署命令同时创建同名容器。

选择 Docker 是为了版本固定和方便维护，数据在宿主机持久化。现有 5.7 无法满足 MySQL checkpoint 库要求（MySQL ≥8.0.19）。参考：[MySQL 官方持久化说明](https://dev.mysql.com/doc/refman/8.4/en/docker-mysql-more-topics.html)、[checkpoint 库兼容性](https://github.com/tjni/langgraph-checkpoint-mysql)。当前任务不需要额外部署 PostgreSQL 或 Redis。

## 本地运行

从各练习目录先安装共享包，再安装该练习：

```powershell
python -m pip install -e ../../shared/database
python -m pip install -e ".[dev]"
```

LangGraph 需要 `python -m pip install -e ".[dev,persistence]"`。仓库根已有本次部署使用的 `.env`；新检出复制 `.env.example` 为 `.env` 并填写密码。环境变量优先于 `.env`；从仓库外启动时显式设置 `DATABASE_URL`。连接信息不要放在命令行、日志或 Git 中。

```powershell
# 在对应练习目录运行；不调用真实模型
python -m tool_loop.demo
python -m lg_lab.persistent_demo pause --thread lesson-1
python -m lg_lab.persistent_demo approve --thread lesson-1
python -m harness_lab.persistence --job lesson-1
python -m uvicorn deploy_lab.app:create_app --factory --host 127.0.0.1 --port 8000
```

Harness 每次推进一步，第三次运行会回放已完成状态。LangGraph 使用新 thread ID 开始新任务，已完成线程不能再次审批；`execution_count` 是数据库台账累计条数。普通内存图示例仍用于离线讲解，持久化入口是 `persistent_demo`。

表用途：`sales/customers` 为工具示例数据，`daily_metrics` 为工作流示例数据，`executions` 为执行台账，`idempotency/jobs/reports` 为 Harness 状态，`requests` 为 API trace，`checkpoints/checkpoint_*` 为 LangGraph 状态。示例行只在不存在时插入，重复启动不覆盖修改后的数据。工作流结果、预算和幂等记录使用事务和行锁；模型 SQL 使用 MySQL 方言，禁止写操作、跨库查询、文件读写及危险函数，并设查询超时。

## 验证与维护

各练习 `python -m pytest tests -q` 只使用临时 SQLite/内存，不依赖虚拟机。真实集成测试须在安装四个练习后，从仓库根显式运行：

```powershell
$env:RUN_MYSQL_INTEGRATION = '1'
python -m pytest shared/database/tests -q
Remove-Item Env:RUN_MYSQL_INTEGRATION
```

集成测试只在随机命名的 `llm_test_*` 数据库中创建和删除测试表，不清空 `llm_learning`。覆盖并发幂等、事务回滚、租户和预算、跨进程审批、提交后崩溃回放以及 API 就绪检查。

服务器维护：`docker logs --tail 50 mysql84`、`docker restart mysql84`、`docker inspect mysql84`。重建容器时必须复用 `/home/mysql84/data` 和环境文件。不要删除该目录；删除容器不会删除绑定目录中的数据。外部 HTTP/付款/邮件副作用仍需下游幂等或 outbox，数据库事务不能独自保证它们只执行一次。
