# 15｜部署与生产工程

**安排：** 第 5 周用 2～3 小时学习 Docker 基础，第 7 周完成部署与生产化整合，P0。后端经验是你的差异化优势。

详细学习：[从本地 FastAPI 到 Docker 的分步部署](./01-FastAPI与Docker实操.md)。

Agent 生产与安全补充阅读见 [微软 AI Agents 教程导读](../06-LangGraph/02-微软AI-Agents教程导读.md)。

## 零基础前置

先理解终端、进程、端口、Client/Server、HTTP 和环境变量。端口可以理解为一台电脑上不同服务的“房间号”；`127.0.0.1:8000` 表示只在本机访问 8000 号端口的服务。

## 最小生产架构

```text
Client → API Gateway/Auth → FastAPI Agent Service
                              ├─ Model Provider
                              ├─ Qdrant / Search
                              ├─ MCP/Business Tools
                              ├─ Postgres/Checkpoint
                              └─ Trace/Metric/Log
```

## 必须覆盖

- Docker、依赖锁、配置分层、启动/就绪/存活检查。
- API 鉴权、tenant 隔离、RBAC、secret 管理和审计。
- timeout、有限重试、退避、熔断、限流、并发和背压。
- 有副作用请求的幂等、审批、补偿；长任务用队列/状态机。
- streaming 断连处理、任务取消和 checkpoint 恢复。
- prompt injection、tool injection、SSRF、任意文件/命令执行防护。
- 缓存、模型路由/降级、token 预算和成本告警。
- logs、metrics、traces 关联；敏感数据脱敏和保留周期。

## Docker 验收

- 新机器按 README 一条主命令可启动依赖和服务。
- 不把 API key 写入镜像或 Git。
- 服务启动后跑 smoke test；依赖不可用时 readiness 失败而不是假健康。
- 失败请求能通过 trace ID 定位到模型、检索、工具或业务层。

## 面试重点

- Java 服务与 Python Agent 怎样划分边界？
- 如何控制长任务、并发、成本和状态？
- 模型 provider 限流/故障时如何降级？
- 如何防止 Agent 通过工具越权和数据外泄？

## 资料怎么用

| 阶段/优先级 | 资料 | 它是干什么的 | 零基础怎么使用 |
|---|---|---|---|
| API/P0 | [FastAPI Deployment](https://fastapi.tiangolo.com/deployment/) | 解释 FastAPI 服务从开发运行到生产部署时的进程、重启、HTTPS、容器等问题 | 先完成本地 `/health`，再读 Concepts。不要一开始研究 Kubernetes；先理解开发 `--reload` 为什么不能直接用于生产 |
| 容器/P0 | [Docker Docs](https://docs.docker.com/) | Docker 官方总文档，讲镜像、容器、Dockerfile、网络、volume 和 Compose | 先完成 Get Started 的 image/container/Dockerfile 三部分；能把 FastAPI 装进镜像并运行后，再学 Compose |
| 观测/P1 | [OpenTelemetry Python](https://opentelemetry.io/docs/languages/python/) | 统一生成和传递 traces、metrics、logs，帮助定位一次 Agent 请求经过哪些组件 | 项目跑通后看 Getting Started。先给 HTTP 和工具调用加 trace ID；Collector/后端平台以后再学 |
| 安全/P0 | [OWASP Top 10 for LLM Applications](https://genai.owasp.org/llm-top-10/) | 总结 Prompt Injection、敏感信息泄露、供应链、过度授权等大模型应用风险 | 每次读一个风险，把它转成项目攻击样本和防护测试。重点先看 Prompt Injection、Sensitive Information Disclosure、Excessive Agency |
| 工程化/P1 | [Made With ML：MLOps Course](https://madewithml.com/courses/mlops/) | 从产品、数据、测试、版本到服务、监控和 CI/CD 的开源工程课程 | 选 testing、serving、monitoring 三块映射到 Agent 项目，不必完成模型训练主线 |
| 工程化/P2 | [MLOps Zoomcamp](https://github.com/DataTalksClub/mlops-zoomcamp) | 免费生产化课程，包含部署、工作流、监控等较完整实践 | 8 周内只按薄弱点查；不要再开启一条 9 周完整主线 |

部署学习不要只追求“公网能访问”。真正的验收还包括密钥不泄露、故障能退出、权限有效、日志可定位和镜像可复现。
