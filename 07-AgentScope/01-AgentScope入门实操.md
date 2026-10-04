# AgentScope 安装、概念与对照实验

## 1. 安装前

AgentScope 2.x 要求和 API 以 [官方文档](https://docs.agentscope.io/) 为准。本工程的验证基线是 `2.0.4.post1`，不是“当前最新版”；先使用已验证版本，再在独立环境试升级：

```powershell
conda activate llm-learning
python -m pip install "agentscope==2.0.4.post1"
python -c "import agentscope; print('AgentScope import OK')"
```

不要同时打开历史 ModelScope-Agent 教程照抄导入路径。

## 2. 核心对象

- Message：谁发送、内容、角色、可能的多模态部分。
- Model：不同模型 provider 的适配。
- Formatter：把消息转换为特定模型需要的格式。
- Tool：Agent 可调用的受控能力。
- Agent：封装推理、工具、memory 和状态。
- Workflow：routing、handoff、并发和多 Agent 交互。

## 3. 学习步骤

1. 按 Tutorial 创建一个不带工具的 Agent，打印输入/输出消息。
2. 加入无副作用的指标定义工具，观察工具 schema 与调用轨迹。
3. 加入 session/state，关闭重开后验证状态是否符合预期。
4. 用 routing 处理“知识问答”和“数据查询”两类任务。
5. 使用 tracing/Studio 查看一次失败流程。

## 4. 多 Agent 实验

任务：生成 ClickHouse SQL 并审核。

- 方案 A：单 Agent 生成，确定性 SQL Guard 检查。
- 方案 B：生成 Agent + Review Agent + 同一确定性 Guard。
- 方案 C：LangGraph 显式生成/审核节点。

比较 30 条样本的 execution accuracy、安全违规率、平均模型调用次数、token、延迟和失败定位时间。Review Agent 不能替代确定性 Guard。

配套工程已把阶段 B 拆成 `metric/knowledge specialist → review agent` 两段，并由普通 Python Coordinator 控制超时、消息长度和 handoff 次数。学习时先运行：

```powershell
cd 07-AgentScope/agentscope-practice
python -m as_lab.demo
python -m pytest -q tests/test_multi_agent_workflow.py
```

重点不是背 AgentScope API，而是观察三种边界：Agent 间只传完成任务所需的消息；审核者没有业务工具权限；任一 Agent 超时或返回错误协议时，请求有限失败而不是继续自由对话。

## 5. 常见误区

- 角色多不等于能力强；角色上下文会增加成本和信息丢失。
- “辩论后达成一致”不是事实验证。
- 并发 Agent 访问相同副作用工具时要处理锁、幂等和资源上限。
- 框架支持 MCP/A2A/Skills 不代表你的业务自动具备安全边界。

## 6. 验收

能用数据回答：AgentScope 多 Agent 相对单 Agent 是否提高本任务质量？提高来自角色分工、更多采样还是额外验证？付出了多少成本？
