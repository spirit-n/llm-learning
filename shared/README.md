# 真实模型实验的统一配置

04–13 章的工程能力、阅读入口和最近验证结果见 [工程学习与验收](04-13工程学习与验收.md)。

03～13 章中需要模型参与的工程，其 `tests_live/` 共用 [live_llm.py](./live_llm.py)。普通 `tests/` 始终离线、快速、可重复；`tests_live/` 只有显式指定目录时才会调用真实模型，因此可能产生费用。

日常运行只需要配置下面四项，不提供 provider、端点、模型或密钥默认值：

```powershell
$env:LLM_BASE_URL = "https://provider.example.com/v1"
$env:LLM_MODEL = "provider-model-name"
$env:LLM_API_KEY_ENV = "PROVIDER_API_KEY"
$env:PROVIDER_API_KEY = "你的密钥"
```

这里 `LLM_API_KEY_ENV` 保存的是“密钥变量的名字”，程序会根据它找到真正保存 key 的 `PROVIDER_API_KEY`。这两个名称必须对应：如果前者写的是 `MY_API_KEY`，第四行也必须改成 `$env:MY_API_KEY`。

然后进入某个练习工程运行：

```powershell
python -m pip install -e ".[dev,live]"
python -m pytest -q tests_live -m live
```

## 你当前使用的四项

| 环境变量 | 状态 | 用途 |
|---|---|---|
| `LLM_BASE_URL` | 必填 | OpenAI-compatible API 根地址；程序自动追加 `/chat/completions` |
| `LLM_MODEL` | 必填 | 实际调用的模型名 |
| `LLM_API_KEY_ENV` | 必填 | 保存“真正密钥变量”的名字，例如 `PROVIDER_API_KEY` |
| `PROVIDER_API_KEY` | 必填 | 真正的密钥；变量名必须与 `LLM_API_KEY_ENV` 的值一致 |

## 暂时不需要配置的可选项

| 环境变量 | 默认值 | 什么时候使用 |
|---|---|---|
| `LLM_CHAT_COMPLETIONS_URL` | 空 | provider 只给完整 `/chat/completions` 地址时，用它代替 `LLM_BASE_URL` |
| `LLM_API_KEY` | 空 | 想直接使用统一 key 变量时，用它代替 `LLM_API_KEY_ENV` 和 provider key 变量 |
| `LLM_TIMEOUT_SECONDS` | `60` | 请求超时 |
| `LLM_TEMPERATURE` | `0` | 采样温度 |
| `LLM_MAX_TOKENS` | `512` | 最大输出 token |
| `LLM_EXTRA_HEADERS_JSON` | 空 | 特殊 provider 需要的附加请求头 JSON |

例如以后切换到另一个兼容端点，不需要修改测试代码：

```powershell
$env:LLM_BASE_URL = "https://another-provider.example.com/v1"
$env:LLM_MODEL = "another-model-name"
$env:LLM_API_KEY_ENV = "OTHER_PROVIDER_API_KEY"
$env:OTHER_PROVIDER_API_KEY = "你的密钥"
python -m pytest -q tests_live -m live
```

若 provider 给的是完整地址，则改设 `LLM_CHAT_COMPLETIONS_URL`。端点、模型名或密钥任一缺失时，notebook 和显式运行的 live 测试都会直接报错，不会调用网络；日志和异常摘要也不会主动输出密钥。

## 2026-10-04：保持配置，补齐调用证据

上述四项配置不变，仍默认调用 Chat Completions；不要求新 key，不自动选模型，也不探测或切换端点。

- `client.chat(messages)` 仍返回原来的 message 字典，各章旧调用方式不用改。
- `client.chat_result(messages)` 额外返回 `usage`、实际返回的 `model`、响应/请求 ID、`finish_reason`、耗时和尝试次数。用量缺失表示**未知**，不是 0；推理 token 不重复加总，也不在本地猜价格。
- 429 与 500/502/503/504 最多尝试 3 次，尊重 `Retry-After`；超过等待预算就失败。401/403、参数错误、超时和网络异常不自动重试。推理请求的重试可能增加费用，**不代表写工具可以自动重试**。
- 总等待预算默认取已有的 `LLM_TIMEOUT_SECONDS`，可用代码中的 `RetryPolicy` 调整；这是请求/退避预算，不是能强杀底层网络或远端推理的硬截止。持续 429 应降低并发、输出预算或查看供应商配额，不要无限重试。
- `JsonlEventSink` 是显式启用的本地 JSONL 元数据日志，不保存 Prompt、工具参数、返回正文或请求头。已知凭据会替换；它不是通用 PII 检测器或生产日志平台。

```python
from shared.live_llm import LiveLLMSettings, OpenAICompatibleChatClient
from shared.llm_support import JsonlEventSink, RetryPolicy

client = OpenAICompatibleChatClient(
    LiveLLMSettings.from_env(),
    retry_policy=RetryPolicy(max_attempts=3),
    event_sink=JsonlEventSink("artifacts/model_requests.jsonl"),
)
# 下行会真实调用模型；普通 pytest tests 不会执行它。
result = client.chat_result([{"role": "user", "content": "用一句话解释工具调用"}])
print(result.usage, result.finish_reason, result.latency_seconds)
```

模型能力不能只凭 OpenAI-compatible 这个名字推断。若供应商文档明确不支持 temperature，或要求 `max_completion_tokens`，可显式传入 `ModelCapabilities(supports_temperature=False, max_tokens_parameter="max_completion_tokens")`；未验证支持工具或 JSON Schema 时，应把对应能力设为 `False`。默认能力配置仅保留旧请求行为，不是能力探测结果。

### 可选 Responses 协议对照

[responses_llm.py](./responses_llm.py) 是独立适配器，不替换当前接口，也不要求增加环境变量。只有确认供应商/模型支持时，才用 `ResponsesClient(settings, endpoint="已核验的完整 Responses 地址")` 手工实验。`input/output` 是 typed items；不能只更改 URL 并继续发送 Chat 格式。

工具返回使用 `function_call_output` 和原 `call_id`；继续对话时保留全部 `result.output_items`，包括 opaque reasoning item，而不是只保存最终文本。这里使用 `store=False`，请求 encrypted reasoning continuation，不展示推理正文。调用方仍须校验工具参数、鉴权、限步，并检查 `finish_reason`（Responses 中对应 status）；`incomplete` 或空文本不能算任务成功。

```python
# 示意续接，lookup_result 必须来自已经校验、授权的本地工具执行。
next_input = [*previous_input, *result.output_items,
              {"type": "function_call_output", "call_id": call_id, "output": lookup_result}]
```

接口差异依据：[迁移指南](https://developers.openai.com/api/docs/guides/migrate-to-responses)、[工具调用](https://developers.openai.com/api/docs/guides/function-calling)。本轮仅验证模拟 HTTP 合约，未验证当前供应商的 Responses 支持。

### 不花模型费用的公共层验证

在仓库根目录：

```powershell
python -m pytest shared/tests -q
```

这些测试使用假响应、假密钥，不读取真实凭据，也不连接模型。03 章 live 测试显式运行后会追加 `03-Function-Calling/tool-calling-practice/artifacts/live_requests.jsonl`；文件已忽略，`-s` 只是让终端显示路径。
