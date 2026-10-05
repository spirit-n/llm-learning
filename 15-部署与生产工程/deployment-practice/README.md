# 离线 FastAPI → Docker 部署练习

正常运行统一使用 `192.168.11.8:3306` 的持久化 MySQL；配置与安装说明见 [共享数据库文档](../../shared/database/README.md)。先执行 `python -m pip install -e ../../shared/database`，再安装本工程。离线测试显式使用临时 SQLite 或内存。

这里不读取模型配置、不调用模型、不需要 GPU。先验证部署与故障语义，再把已经学过的 Agent 接入服务层；`/demo` 返回固定教学答案，不是聊天模型。仅供本机练习，尚未实现登录鉴权，不应暴露公网。

在此工程目录，推荐独立 Python 3.12 环境：

```powershell
python -m pip install -e ".[dev]"
python -m pytest tests -q
python -m uvicorn deploy_lab.app:create_app --factory --host 127.0.0.1 --port 8000
```

另一个终端：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod http://127.0.0.1:8000/ready
Invoke-RestMethod http://127.0.0.1:8000/demo -Method Post -ContentType 'application/json' -Body '{"question":"tool calling"}'
```

`/health` 只证明进程活着；`/ready` 查询远程 MySQL 的 requests 表，存储丢失返回 503。`X-Trace-Id` 与返回体关联，数据库只记录 ID，不存问题正文。测试会主动移除临时数据库，验证健康与就绪的区别。

## 容器练习（需要本机 Docker Engine）

```powershell
docker compose up --build -d
docker compose ps
docker compose logs --tail 30 app
```

复用上面的三条请求做 smoke。Compose 只发布到 127.0.0.1；非 root 用户、只读根文件系统、远程持久化 MySQL，不把模型环境变量或 `.env` 复制到镜像。停止应用用 `docker compose down`；MySQL 数据在虚拟机宿主机上，不依赖应用容器。

## 阅读与验收

1. `src/deploy_lab/app.py`：请求校验 → trace ID → 存储就绪 → 受控错误。
2. `tests/test_app.py`：正常请求、缺失依赖、非法参数。
3. `Dockerfile` 与 `compose.yaml`：进程、健康检查、用户、端口和数据库配置。

依赖边界：`pyproject.toml` 固定两个直接运行依赖版本，**不是完整传递依赖锁**；基础镜像 tag 也不是不可变 digest。生产验收还需在目标 Linux/Python 平台生成带哈希的完整锁、固定镜像 digest、扫描依赖，再复测。此轮验证了进程内 HTTP 测试，未宣称已在 Docker 中构建运行；无 TLS、认证、限流、队列或生产级日志平台。
