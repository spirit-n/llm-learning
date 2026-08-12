# 设计一个可测量的 Context Builder

## 1. 输入和输出

输入：任务、用户/租户、权限、当前状态、检索候选、工具结果、历史和 token 上限。

输出不应只有一个长字符串，还应包含 manifest：

```json
{
  "context_version": "v3",
  "tenant": "tenant-a",
  "task_source": "BuildRequest.task",
  "task_sha256": "任务正文的 SHA-256",
  "included": [
    {"id": "policy-v2", "layer": "system", "source": "policy-v2", "tokens": 320, "position": 0},
    {"id": "__build_request_task__", "layer": "task", "source": "BuildRequest.task", "tokens": 80, "position": 1}
  ],
  "total_tokens": 400,
  "dropped": [{"id": "old-history-1", "reason": "token_budget"}]
}
```

manifest 让一次回答可追踪：模型究竟看到了什么、什么被丢弃。
其中 `BuildRequest.task` 本身会成为必需的 TASK section，并与其他 section 一起参与排序和 token 预算；manifest 保存摘要而不重复泄露完整任务正文。改变 task 会同时改变最终 Context 和 `task_sha256`。

## 2. 构建顺序

1. 确定任务与完成条件。
2. 绑定用户身份和不可越过的权限。
3. 加载最小系统规则。
4. 按任务检索 schema、指标和知识。
5. 合并工具结果与任务状态。
6. 去重、排序、冲突处理、注入标记和脱敏。
7. 先验证必需项，再分配整体/分层 token 预算，输出 manifest 与裁剪诊断。

权限、时效检查必须发生在摘要和拼接之前。标记为 `required` 的规则若越权、过期或超预算，应稳定失败；不能悄悄删掉后让模型在缺少安全规则的情况下继续回答。异常信息只记录 item ID 和策略 reason，不回显敏感正文。

## 2.2 来源优先级、版本与时效

冲突排序至少拆成三个维度：

1. **来源类型**：系统策略、运行时状态、权威目录、工具结果、普通检索和记忆不是同一等级。
2. **来源内版本**：同一个权威目录里，v3 通常胜过 v2。
3. **时效**：`expires_at` 已过期、超过 `max_age_seconds` 或时间戳来自未来都不能参与竞争。

不要只比较版本号。低权威来源可以伪造更大的版本。为了让时效判断可回放，请由请求显式传入 `as_of`；同一输入在测试和事故复盘时应产生相同 manifest。

## 2.1 微软课程补充：写入、选择、压缩、隔离

[Microsoft Context Engineering 章节](https://github.com/microsoft/ai-agents-for-beginners/tree/main/12-context-engineering) 将核心动作概括为四类：

- **Write（写入）**：把计划、工具结果和关键事实写到可恢复状态/外部存储，不完全依赖模型上下文。
- **Select（选择）**：当前一步只取需要的 schema、记忆、工具和文档。
- **Compress（压缩）**：摘要旧历史、长文档和工具输出，同时保留来源 ID 以便回看原文。
- **Isolate（隔离）**：把不同任务、子 Agent、用户/租户和不可信数据分开，避免相互污染与越权。

每次 Context Builder 改动都应指出属于哪一类动作，并用指标证明不是“感觉更整洁”。

## 3. Token 预算示例

假设模型窗口允许输入 8,000 token：先用 `reserved_tokens=500` 给输出和协议包装留缓冲，剩余 7,500 再分配 system 800、任务 500、领域规则 1,000、检索 3,500、工具结果 1,200、历史 500。预算不是固定比例，应由任务评测调整。

整体预算只能保证“不超窗口”，不能防止一个长 retrieved section 抢走全部空间。关键层应再配 `layer_budgets`。Manifest 要分别记录 input limit、reserved、available、used、remaining、各层用量和结构分隔符开销。

## 4. 历史与记忆

- 最近原始轮次：保留局部措辞。
- 结构化状态：任务目标、已完成步骤、关键实体。
- 摘要：压缩旧内容，但要保存来源/可回溯 ID。
- 长期记忆：只存经过筛选、允许持久化的信息；有修改和删除机制。

聊天记录不是状态，摘要也不是事实数据库。

## 5. 五个对照实验

全量 schema vs 按需检索；全历史/滑动窗口/状态摘要；工具原文压缩 vs 结构化摘要；只看版本号 vs 显式来源权威；整体预算 vs 分层预算。报告质量、token、裁剪量、丢弃原因、延迟和失败类型。

## 6. 注入与权限

检索内容属于不可信数据。边界不能只是可被正文写出闭合标签的 XML 外壳；工程将来源和正文放入 JSON 数据信封，并转义正文中的换行与 `<>[]` 控制字符，确保 `</untrusted-data>` 或 `[SYSTEM]` 只能作为数据。更重要的是，不把密钥或无权数据放入 context，不给 Agent 无需使用的高风险工具。

### 四类常见 Context 失败

- **Poisoning（污染）**：错误/恶意信息进入上下文或长期记忆。
- **Distraction（干扰）**：相关但不必要的内容太多，模型忽略关键证据。
- **Confusion（混淆）**：同时给太多工具、schema 或目标，模型选错。
- **Clash（冲突）**：系统规则、文档、历史或工具结果互相矛盾。

为四类各写一条测试样本。解决方案分别可能是来源校验、选择/压缩、减少工具集、版本/优先级和澄清，而不是统一加一句“请仔细判断”。

## 7. 验收

给定一次错误回答，能通过 manifest 证明它是“模型没看到证据”“看到了错误版本”“工具输出被截断”还是“模型未忠于上下文”。同时能回答：

- 哪条内容因 tenant/role、过期、冲突、重复、分层预算或整体预算被丢弃？
- 压缩前后各有多少 token，保留比例是多少，去哪里回查原文？
- 为什么低权威 v99 没有覆盖权威目录 v2？
- 为什么必需规则不可见时系统直接失败，而不是继续请求模型？

完整实现与 34 条离线用例见 [context-builder-practice](./context-builder-practice/README.md)。
