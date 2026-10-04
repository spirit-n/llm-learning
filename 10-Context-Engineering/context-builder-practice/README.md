# 可审计 Context Builder 练习

## 2026-10：多轮压缩恢复与按需工具目录

```powershell
python -m context_lab.compaction
python -m context_lab.tool_discovery
python -m pytest tests/test_compaction.py tests/test_tool_discovery.py -q
```

先看 `compaction.py`：可信事件 → 目标/决定/待办/证据引用 → JSON checkpoint → 两次恢复执行。实验会比较事实保留、恢复是否成功，以及故意删掉口径/待办/证据后是否拒绝；丢弃的讨论文本不能暗中改变任务。

再看 `tool_discovery.py`：先按权限过滤工具目录，再关键词搜索与按需加载 schema，比较定义长度、工具召回、精确率与额外发现步骤。最终执行仍要重新鉴权。这里是确定性机制实验，不是 LLM 摘要质量、真实 tokenizer 计数或网络延迟实测，也不是供应商 Tool Search API 的兼容实现。

模型原生 compaction/tool search 作为可选 P3 能力，见 [技术雷达](../../18-前沿技术雷达/02-2026-10技术栈更新与采用清单.md)。真实摘要实验应使用同一多轮轨迹，评估跨压缩边界任务成功率，不只展示节省比例。

这个工程不把 Context Engineering 简化成“把字符串按优先级拼起来”。它实现了一条可回放的构建流水线：先做权限和时效过滤，再按来源权威解决冲突/重复，随后压缩、分配整体与分层 token 预算，最后输出 Context、manifest 和裁剪诊断。

默认 demo 与单元测试完全离线、同一输入输出确定。`tests_live/` 只验证真实模型是否采用已经筛选好的 Context，不让模型参与权限或冲突裁决。

## 运行

```powershell
cd 10-Context-Engineering/context-builder-practice
python -m pip install -e ".[dev]"
python -m context_lab.demo
python -m pytest -q
```

## 构建流水线

```text
BuildRequest
  → task / tenant 输入规范化
  → 把 task 生成为必需的 TASK section
  → tenant / role 权限过滤
  → as_of 时效检查（expired / stale / future）
  → 来源权威 + 版本解决冲突
  → NFKC 内容指纹或 dedupe_key 去重
  → 脱敏、压缩、不可信数据 JSON 信封隔离
  → required、层级、相关度和来源排序
  → 整体预算 + reserved_tokens + layer_budgets
  → context + manifest(v3) + diagnostics
```

几个关键工程决定：

- `BuildRequest.task` 会生成来源为 `BuildRequest.task` 的必需 TASK 段，并参与排序、整体/分层预算。manifest v3 记录它的位置、token、来源与 SHA-256；修改 task 必然改变 Context 和审计摘要。
- `task`、`tenant` 会先去除首尾空白并拒绝空白字符串；tenant 还禁止换行，避免构造无法归属或伪造元数据边界的请求。
- `source_kind` 与 `version` 分开。权威指标目录的 v2 不会被普通网页检索片段的 v99 覆盖。
- 有 `expires_at` 或 `max_age_seconds` 时必须传 `BuildRequest.as_of`。Builder 不偷偷读取当前时间，历史请求才能稳定回放。
- `required` 内容过期、冲突失败或超预算时直接抛错，不静默降级成“缺少安全规则也继续回答”。
- tenant/role 不可见的 required 内容同样显式失败且不回显正文；敏感工具结果会遮盖邮箱、手机号、API key、Bearer/sk-* 等常见凭据。
- `reserved_tokens` 给模型输出和协议包装留空间；`layer_budgets` 防止长检索材料吃光工具结果/领域规则的份额。
- token 预算统计渲染后的来源头和 section 分隔符；`token_override` 只用于构造确定性边界测试。
- 压缩后保留 `[原文:source]`，manifest 同时记录 `original_tokens`、`tokens` 和 `truncated_tokens`。
- 不可信正文不是简单套一层可自行闭合的 XML 标签，而是编码成单行 JSON 数据信封；正文中的换行、`<>[]` 与伪造 `[SYSTEM]` 都只能作为 JSON 字符串数据存在。

## 来源优先级

默认冲突优先级由高到低：

```text
system_policy
→ runtime_state
→ authoritative_catalog
→ tool_result
→ retrieval
→ memory
→ user_content
→ unknown
```

只有来源级别相同，才继续比较版本、更新时间、可信度和业务优先级。可以通过 `ContextBuilder(source_precedence=...)` 覆盖局部等级，但应配套冲突测试。

## 最小调用

```python
from datetime import datetime, timezone

from context_lab import BuildRequest, ContextBuilder, ContextItem

result = ContextBuilder(max_item_tokens=120).build(
    BuildRequest(
        task="解释成功率",
        tenant="tenant-a",
        roles={"analyst"},
        token_budget=800,
        reserved_tokens=120,
        layer_budgets={"retrieved": 300, "tool": 180},
        as_of=datetime(2026, 8, 12, tzinfo=timezone.utc),
        items=[
            ContextItem(
                id="metric-v2",
                layer="domain",
                source="metric-catalog",
                source_kind="authoritative_catalog",
                content="成功率=成功请求数/总请求数",
                version=2,
                conflict_key="success-rate",
                required=True,
            )
        ],
    )
)
```

不要在生产代码中使用 `token_override`。应把 `estimate_tokens` 替换为目标模型 tokenizer，其他选择、预算和 manifest 结构可以保留。

## Manifest 怎么排错

`manifest.included` 能回答：用了哪个来源/版本、是否脱敏或压缩、压缩损失多少。`manifest.dropped` 会给出稳定 reason 与 detail，例如：

| reason | 含义 | 优先检查 |
|---|---|---|
| `permission_tenant` / `permission_role` | 权限不可见 | 检索是否在权限域内执行 |
| `expired` / `stale` | 来源过期或太旧 | 刷新来源，不要只提高 priority |
| `conflict_lower_authority` | 冲突中败给更权威来源 | winner、source_kind、版本 |
| `duplicate_lower_authority` | 同一事实重复 | dedupe_key/内容指纹是否合理 |
| `layer_token_budget` | 单层配额触顶 | 分层预算是否适合当前任务 |
| `token_budget` | 整体可用预算不足 | 排序、reserved_tokens、窗口大小 |

`diagnose_build(manifest)` 会汇总预算利用率、drop reason、每条压缩的保留比例和诊断建议。`diagnose_evidence(...)` 进一步区分“没看到”“版本不对”“被压缩需回查原文”和“模型看到了但没采用”。

## 五组离线实验

`experiments.py` 的 `run_all_experiments()` 覆盖：

1. 全量 schema 与相关性选择。
2. 全历史、滑动窗口与结构化状态摘要。
3. 工具原始明细压缩与结构化摘要。
4. 只看版本号与加入来源权威后的冲突结果。
5. 只用整体预算与增加分层预算后的证据保留情况。

实验报告 token、included IDs、drop reasons 和 truncated tokens，不只比较一段回答“看起来好不好”。

## 建议阅读顺序

1. `models.py`：ContextItem、预算报告和 manifest v3。
2. `builder.py`：权限/时效、来源优先级、去重/冲突、压缩和预算控制流。
3. `diagnostics.py`：如何解释裁剪与回答失败。
4. `experiments.py`：五组可重复对照实验。
5. `tests/test_context_builder.py`：34 条离线边界测试。

## 真实模型实验

`tests_live/test_live_context_answer.py` 先由 Builder 解决冲突和筛选，再让模型严格返回答案与 source IDs。它继续使用仓库统一的 `LLM_BASE_URL`、`LLM_MODEL`、`LLM_API_KEY_ENV` 和对应密钥变量，不写死端点、模型或 key。配置见 [统一 live 配置](../../shared/README.md)：

```powershell
python -m pip install -e ".[dev,live]"
python -m pytest -q tests_live -m live
```
