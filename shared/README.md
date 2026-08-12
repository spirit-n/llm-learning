# 真实模型实验的统一配置

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
