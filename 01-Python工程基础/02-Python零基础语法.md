# Python 零基础语法

这不是完整语言手册，而是后续写 LLM 应用所需的最小语法。每段代码都应亲自运行和修改。

## 1. 变量与基础类型

```python
name = "RAG"          # str
week = 1              # int
temperature = 0.2     # float
enabled = True        # bool
nothing = None        # NoneType

print(type(name))
print(f"第 {week} 周学习 {name}")
```

Python 不写 `String name = ...`，但可使用类型标注提高可读性：

```python
name: str = "Agent"
week: int = 1
```

类型标注默认不会自动阻止错误值；Pydantic 才会在运行时做数据校验。

## 2. 容器

```python
topics = ["Python", "RAG", "Agent"]
config = {"model": "demo-model", "temperature": 0.2}
unique_tags = {"rag", "agent", "rag"}
point = (10, 20)

print(topics[0])
print(config["model"])
print(unique_tags)
```

- `list`：有序、可修改。
- `dict`：键值映射，JSON 处理极常用。
- `set`：去重和集合运算。
- `tuple`：有序、通常不修改。

## 3. 条件与循环

```python
score = 82

if score >= 90:
    level = "优秀"
elif score >= 60:
    level = "通过"
else:
    level = "需复习"

for index, topic in enumerate(topics, start=1):
    print(index, topic)
```

Python 用缩进表示代码块，推荐 4 个空格，不混用 Tab。

## 4. 函数

```python
def build_message(question: str, source: str = "unknown") -> dict[str, str]:
    """构造结构化消息。"""
    if not question.strip():
        raise ValueError("question 不能为空")
    return {"question": question, "source": source}

message = build_message("什么是 RAG？", source="notes")
```

注意默认参数、关键字参数、返回类型和异常。不要把可变对象 `[]`/`{}` 作为默认参数。

## 5. 异常处理

```python
try:
    value = int("abc")
except ValueError as exc:
    print(f"转换失败：{exc}")
finally:
    print("无论成功失败都会执行")
```

工程中不要写空的 `except:` 后忽略错误。应捕获具体异常，记录必要上下文，再决定重试、降级或返回。

## 6. 类与数据模型

普通类：

```python
class Tool:
    def __init__(self, name: str):
        self.name = name

    def run(self, text: str) -> str:
        return f"{self.name}: {text}"
```

Pydantic 用于外部输入校验：

```python
from pydantic import BaseModel, Field

class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    temperature: float = Field(default=0.2, ge=0, le=2)
```

## 7. 模块和入口

`math_utils.py`：

```python
def add(a: int, b: int) -> int:
    return a + b
```

另一个文件：

```python
from math_utils import add

if __name__ == "__main__":
    print(add(1, 2))
```

## 8. 文件与 JSON

```python
import json
from pathlib import Path

path = Path("example.json")
data = {"model": "demo", "enabled": True}
path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
loaded = json.loads(path.read_text(encoding="utf-8"))
```

学习时可运行写文件示例；项目中要校验路径和来源，避免 Agent 任意读写文件。

## 9. 同步与异步的直觉

```python
import asyncio

async def fake_model_call(name: str) -> str:
    await asyncio.sleep(1)
    return f"{name} done"

async def main():
    results = await asyncio.gather(
        fake_model_call("A"),
        fake_model_call("B"),
    )
    print(results)

await main()  # Notebook 中可直接使用 await
```

异步适合等待网络/磁盘 I/O，不会自动加速 CPU 密集计算。真实应用还需要 timeout、并发上限和取消处理。

## 10. 学完后的最低标准

- 看懂函数、类、dict/list、异常和类型标注。
- 能读写 JSON，调用 HTTP API，定义 Pydantic schema。
- 知道环境、解释器、包和 Kernel 的区别。
- 遇到报错先读最后一行异常类型，再向上找自己的代码位置。

继续运行 [python入门实验.ipynb](./python入门实验.ipynb)，不要只阅读。
