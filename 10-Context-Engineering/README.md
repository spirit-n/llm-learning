# 10｜Context Engineering

2026-10 补充：[工程 README](./context-builder-practice/README.md#2026-10多轮压缩恢复与按需工具目录) 增加两次压缩后的任务恢复，以及权限过滤后的按需 schema 加载。验收目标不是“文本变短”，而是下一步仍能正确执行。

**安排：** 第 5 周中段，P1，但原则贯穿全部项目。

详细学习：[设计一个可测量的 Context Builder](./01-Context-Builder实操.md)。

补充教材：微软 AI Agents 课程的 Context 与 Memory 章节已映射在 [中文导读](../06-LangGraph/02-微软AI-Agents教程导读.md)。

配套工程：[context-builder-practice](./context-builder-practice/README.md)。工程以纯 Python 实现必需且可审计的任务段、权限/时效前置过滤、显式来源权威链、确定性去重与冲突处理、不可信数据 JSON 隔离、整体/分层 token 预算、压缩损失诊断和 manifest v3，并覆盖四类 Context 失败。离线实验不依赖模型。

快速开始：

```powershell
cd 10-Context-Engineering/context-builder-practice
python -m pip install -e ".[dev]"
python -m context_lab.demo
python -m pytest -q
```

## 零基础前置

先理解 token、Prompt、RAG、Tool 和聊天历史。可以把 Context 想成“开卷考试时放在桌面的所有材料”，Context Engineering 就是决定带哪些材料、按什么顺序摆放、哪些材料不能带。

## Context 分层

| 层 | 例子 | 风险 |
|---|---|---|
| System | 身份、安全、优先级 | 被低优先级内容覆盖 |
| Task | 当前目标、完成条件 | 目标漂移 |
| Domain | 指标口径、schema、术语 | 过期或越权 |
| Retrieved | RAG chunks、引用 | 噪声、注入、冲突 |
| Tool | SQL 结果、错误摘要 | 过长、敏感数据 |
| Memory | 偏好、历史状态 | 污染、隐私、陈旧 |
| Runtime | 重试数、预算、权限 | 状态不一致 |
| Output Contract | JSON schema、引用要求 | 格式与任务冲突 |

## Context Builder 应有的步骤

1. 根据身份和任务决定可见数据范围。
2. 检索需要的规则、schema 和知识，不整库塞入。
3. 去重、排序、标注来源/版本/信任等级。
4. 对工具输出做结构化裁剪和摘要，保留可验证原始引用。
5. 按 token 预算分配各层，超限时使用明确的丢弃/压缩策略。
6. 记录最终 context manifest，便于复现与审计。

注意：来源优先级不能和文档版本混为一谈。一个未经验证网页的 `v99` 不应覆盖权威指标目录的 `v2`；有过期规则的来源还必须携带可回放的 `as_of`，不能在 Builder 内部偷偷读取当前时间。

## 必做实验

- schema 全量输入 vs 按问题检索。
- 全历史 vs 滑动窗口 vs 状态摘要。
- 工具原始输出 vs 结构化摘要 + 原始结果引用。
- 冲突文档中加入时间、版本和可信级别后比较回答。
- 只有整体预算 vs 为 retrieved/tool/domain 设置分层预算，观察长检索材料是否挤掉工具证据。

配套工程的 `run_all_experiments()` 会统一报告 token、included IDs、drop reasons 和裁剪 token 数，避免只凭一段回答的观感下结论。

## 面试追问

- 长上下文窗口变大后，为什么仍需要 Context Engineering？
- 摘要会丢信息，怎样验证与回溯？
- RAG 检索到用户无权访问的 chunk，生成前过滤是否足够？（不够，应在检索前/检索层执行权限约束。）

## 配套教程怎么用

| 优先级 | 教程 | 它补充什么 | 怎么学 |
|---|---|---|---|
| P0 | [Microsoft Context Engineering](https://github.com/microsoft/ai-agents-for-beginners/tree/main/12-context-engineering) | write/select/compress/isolate 与常见 Context 失败 | 给 poisoning、distraction、confusion、clash 各做一条测试 |
| P1/P2 | [Hugging Face Context Course](https://huggingface.co/learn/context-course/unit0/introduction) | Skills、MCP、Plugins、Subagents、Hooks 和 Nano Harness 的实践课程 | 先 Unit 1/2/6；其他单元按项目需要，不连续通刷 |
