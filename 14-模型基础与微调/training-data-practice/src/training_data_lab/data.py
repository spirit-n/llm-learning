from __future__ import annotations

import json
from dataclasses import dataclass


def validate_example(example: dict) -> None:
    tools = {}
    for tool in example.get("tools", []):
        function = tool.get("function", {})
        name = function.get("name")
        if tool.get("type") != "function" or not name or name in tools:
            raise ValueError("tools 必须有唯一函数名")
        tools[name] = function.get("parameters", {})
    messages = example.get("messages")
    if not isinstance(messages, list) or not messages:
        raise ValueError("messages 必须是非空列表")
    pending = set()
    seen = set()
    assistant_seen = False
    for message in messages:
        role = message.get("role")
        if role not in {"system", "user", "assistant", "tool"}:
            raise ValueError("非法 role")
        if not isinstance(message.get("content", ""), str):
            raise ValueError("本练习只接受文本 content")
        if role == "tool":
            call_id = message.get("tool_call_id")
            if call_id not in pending:
                raise ValueError("工具结果必须关联待完成 tool_call_id")
            pending.remove(call_id)
        elif pending:
            raise ValueError("继续对话前必须补齐工具结果")
        calls = message.get("tool_calls", [])
        if calls and role != "assistant":
            raise ValueError("仅 assistant 可以提出调用")
        for call in calls:
            call_id = call.get("id")
            function = call.get("function", {})
            name, args = function.get("name"), function.get("arguments")
            if not call_id or call_id in seen or name not in tools or not isinstance(args, dict):
                raise ValueError("调用 ID/函数名/参数格式无效")
            schema = tools[name]
            if not set(schema.get("required", [])).issubset(args):
                raise ValueError("调用缺少必需参数")
            if schema.get("additionalProperties") is False and not set(args).issubset(schema.get("properties", {})):
                raise ValueError("调用包含额外参数")
            pending.add(call_id)
            seen.add(call_id)
        assistant_seen |= role == "assistant" and bool(message.get("content", "").strip() or calls)
    if pending or not assistant_seen:
        raise ValueError("样本必须有 assistant 目标且不能缺少工具结果")


@dataclass
class EncodedExample:
    tokens: list[str]
    input_ids: list[int]
    labels: list[int]
    attention_mask: list[int]
    assistant_mask: list[bool]


def encode_example(example: dict, *, max_length: int = 4096, pad_to: int | None = None) -> EncodedExample:
    """Character tokenizer + explicit role markers: a visible teaching template, not an HF tokenizer.

    Never silently truncate targets/tool results. A real trainer must use its model's
    tokenizer, EOS and template generation masks, then inspect the same invariants.
    """
    validate_example(example)
    tokens, mask = ["<bos>"], [False]
    if example.get("tools"):
        tools_text = json.dumps(example["tools"], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        definition = ["<tools>", *tools_text, "<eos>"]
        tokens.extend(definition)
        mask.extend([False] * len(definition))
    for message in example["messages"]:
        role = message["role"]
        tokens.append(f"<{role}>")
        mask.append(False)
        content = message.get("content", "")
        if role == "tool":
            content = json.dumps({"tool_call_id": message["tool_call_id"], "content": content}, ensure_ascii=False)
        if message.get("tool_calls"):
            content += json.dumps(message["tool_calls"], ensure_ascii=False, sort_keys=True)
        body = list(content) + ["<eos>"]
        tokens.extend(body)
        mask.extend([role == "assistant"] * len(body))
    if len(tokens) > max_length:
        raise ValueError("样本超长：先检查目标与工具结果，不能静默截断")
    # Reserved teaching IDs + Unicode code points, stable across samples.
    special = {"<pad>": 0, "<bos>": 1, "<eos>": 2, "<system>": 3, "<user>": 4, "<assistant>": 5, "<tool>": 6, "<tools>": 7}
    ids = [special[token] if token in special else ord(token) + 10 for token in tokens]
    labels = [token_id if learn else -100 for token_id, learn in zip(ids, mask)]
    attention = [1] * len(ids)
    if pad_to is not None:
        if pad_to < len(ids) or pad_to > max_length:
            raise ValueError("padding 长度必须覆盖样本且不超过 max_length")
        n = pad_to - len(ids)
        tokens += ["<pad>"] * n
        ids += [0] * n
        labels += [-100] * n
        attention += [0] * n
        mask += [False] * n
    return EncodedExample(tokens, ids, labels, attention, mask)


def demo_example() -> dict:
    return {"messages": [
        {"role": "user", "content": "营业收入是什么？"},
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": "call-1", "function": {"name": "definition", "arguments": {"metric": "revenue"}}}]},
        {"role": "tool", "tool_call_id": "call-1", "content": "主营业务与其他业务收入，不含增值税"},
        {"role": "assistant", "content": "营业收入包括主营业务与其他业务收入，不含增值税。"}],
        "tools": [{"type": "function", "function": {"name": "definition", "parameters": {
            "type": "object", "properties": {"metric": {"type": "string"}},
            "required": ["metric"], "additionalProperties": False}}}]}


if __name__ == "__main__":
    encoded = encode_example(demo_example())
    print(json.dumps({"tokens": len(encoded.input_ids), "supervised_tokens": sum(encoded.assistant_mask),
                      "model_downloaded": False, "training_performed": False}))
