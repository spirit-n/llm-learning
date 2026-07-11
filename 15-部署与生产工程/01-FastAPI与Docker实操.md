# 从本地 FastAPI 到 Docker 的分步部署

## 1. 本地准备

在 Anaconda Prompt：

```powershell
conda activate llm-learning
python -m pip install fastapi "uvicorn[standard]" pydantic-settings httpx
python -c "import fastapi, uvicorn; print('FastAPI OK')"
```

## 2. 最小应用

`app/main.py`：

```python
from fastapi import FastAPI

app = FastAPI(title="LLM Learning API")

@app.get("/health/live")
def live():
    return {"status": "alive"}

@app.get("/health/ready")
def ready():
    # 后续检查关键依赖；不要执行昂贵模型调用
    return {"status": "ready"}
```

运行：

```powershell
python -m uvicorn app.main:app --reload --port 8000
```

浏览器打开 `http://127.0.0.1:8000/docs`。看到 Swagger 页面且 `/health/live` 返回 200 算成功。`--reload` 只用于开发。

## 3. 配置与密钥

用环境变量/secret manager，不提交 `.env`。仓库只放 `.env.example`：

```text
MODEL_API_KEY=
MODEL_NAME=
DATABASE_DSN=
```

日志中不打印完整请求、API key、连接串和敏感工具结果。

## 4. Dockerfile 思路

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
# 按项目锁文件安装依赖；这里省略具体工具命令
COPY app ./app
USER 10001
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

生产 Dockerfile 应固定/锁定依赖、使用非 root 用户、减少构建上下文、做漏洞扫描，且不把密钥 COPY 进镜像。

## 5. 验收顺序

1. 本地进程通过单元/集成测试。
2. 构建镜像，容器内 smoke test。
3. 不提供数据库时 readiness 失败但 liveness 正常（按实际依赖设计）。
4. 模拟 model 429、tool timeout、客户端取消。
5. 多请求压测，观察 P95、错误率、并发和成本。

## 6. Agent 特有问题

- 一个请求可能运行很久：考虑任务队列、状态查询、取消和 checkpoint。
- streaming 断开：停止下游还是后台继续，要有明确语义。
- 工具副作用：幂等键、审批和补偿。
- 多租户：权限上下文贯穿 RAG、MCP、数据库和 trace。
- provider 故障：有限重试、模型降级和预算保护。

## 7. Windows 常见问题

- `uvicorn` 找不到：使用 `python -m uvicorn`，并检查当前环境。
- import `app` 失败：在包含 `app` 文件夹的项目根目录运行。
- 端口占用：改端口或查明占用进程，不要随意结束未知系统进程。
- Docker Desktop 未启动：先启动并等待引擎 ready，再执行 Docker 命令。

资料：[FastAPI Deployment](https://fastapi.tiangolo.com/deployment/)、[Docker Get Started](https://docs.docker.com/get-started/)。
