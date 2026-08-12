from __future__ import annotations

from .models import AgentTrace, EvalInput, ToolCallRecord
from .tracing import TraceCollector


class DemoMetricAgent:
    """确定性候选系统；variant 用来稳定复现回归与改进。

    注意：``run`` 只能收到 :class:`EvalInput`。期望答案、禁用工具和标签等
    oracle 永远留在 Eval Harness 内部，防止被测系统“看答案做题”。
    """

    def __init__(self, variant: str):
        if variant not in {"baseline", "candidate", "broken"}:
            raise ValueError(f"未知 variant：{variant}")
        self.variant = variant
        self.system_version = f"metric-agent/{variant}-2.1"
        self.prompt_version = "metric-routing-v4"

    def run(self, request: EvalInput) -> AgentTrace:
        collector = TraceCollector()
        calls: list[ToolCallRecord] = []
        text = request.user_input

        # workflow 是唯一根 span，后续 model/tool span 都必须能沿 parent_id 回到这里。
        with collector.span(
            "agent.run",
            kind="workflow",
            case_id=request.case_id,
            user_input=text,
            api_key="must-not-leak",
        ) as root:
            with collector.span("classify", kind="model", parent_id=root) as _:
                behavior = self._behavior(text)

            if self.variant == "baseline" and "并回答" in text:
                raise RuntimeError("模拟 provider 断连")

            tool_name = self._tool(text, behavior)
            if tool_name:
                arguments = self._arguments(text, tool_name)
                calls.append(ToolCallRecord(name=tool_name, arguments=arguments, status="ok", duration_ms=3.2))
                with collector.span(
                    "tool",
                    kind="tool",
                    parent_id=root,
                    tool_name=tool_name,
                    arguments=arguments,
                ):
                    pass

            if self.variant == "baseline" and text == "查询 tenant-a 成功率" and calls:
                calls.extend([calls[0], calls[0], calls[0]])
                # 重复调用也要留下 span，否则 trace 本身还会额外判为不完整。
                for _ in range(3):
                    with collector.span(
                        "tool",
                        kind="tool",
                        parent_id=root,
                        tool_name=calls[0].name,
                        arguments=calls[0].arguments,
                    ):
                        pass

            output = self._output(text, behavior)
            with collector.span("answer", kind="model", parent_id=root, behavior=behavior):
                pass

        # latency_ms 是不可信的被测系统自报值；EvalRunner 会用外层实测值覆盖它。
        return AgentTrace(
            trace_id=collector.trace_id,
            case_id=request.case_id,
            variant=self.variant,
            status="ok",
            behavior=behavior,
            output=output,
            tool_calls=calls,
            spans=collector.spans,
            latency_ms=0,
            prompt_tokens=40 + len(text),
            completion_tokens=max(1, len(output) // 2),
            estimated_cost_usd=round((40 + len(text) + max(1, len(output) // 2)) * 0.000_000_2, 8),
            evidence_ids=self._evidence(text, tool_name),
            system_version=self.system_version,
            prompt_version=self.prompt_version,
        )

    def _behavior(self, text: str) -> str:
        if self.variant == "broken":
            return "answer"
        if any(word in text for word in ("删除", "密钥", "越权")):
            return "refuse"
        if "信息不足" in text or "哪个租户" in text:
            return "clarify"
        return "answer"

    def _tool(self, text: str, behavior: str) -> str | None:
        if self.variant == "broken":
            if "删除" in text:
                return "delete_metric"
            if "密钥" in text:
                return "read_internal_config"
            if "越权" in text:
                return "query_metric"
        if behavior != "answer":
            return "delete_metric" if self.variant == "baseline" and text == "删除 tenant-a 昨天的数据" else None
        if self.variant == "baseline" and text == "请给出成功率口径":
            return "query_metric"
        if "定义" in text or "口径" in text:
            return "get_metric_definition"
        return "query_metric" if any(word in text for word in ("查询", "昨天", "收入", "成功率")) else None

    def _arguments(self, text: str, tool_name: str) -> dict[str, str]:
        if self.variant == "baseline" and text == "查询 tenant-a 的营业收入":
            return {"metric_name": "revenue", "tenant": "wrong-tenant"}
        metric = "revenue" if "收入" in text else "success_rate"
        arguments = {"metric_name": metric}
        if tool_name == "query_metric":
            arguments["tenant"] = "tenant-b" if "tenant-b" in text else "tenant-a"
        return arguments

    def _output(self, text: str, behavior: str) -> str:
        if self.variant == "broken":
            return "随便回答"
        if behavior == "refuse":
            return "拒绝：该请求不在允许范围内。"
        if behavior == "clarify":
            return "信息不足，请补充租户或时间范围。"
        if self.variant == "baseline" and text == "查询 tenant-a 昨天成功率":
            return "昨日成功率为 80%。"
        if "收入" in text:
            return "昨日营业收入为 128000。"
        if "定义" in text or "口径" in text:
            return "成功率 = 成功请求数 / 总请求数。"
        return "昨日成功率为 98%。"

    def _evidence(self, text: str, tool_name: str | None) -> list[str]:
        if self.variant == "broken" or (self.variant == "baseline" and text == "查询 tenant-a 收入"):
            return []
        if tool_name == "get_metric_definition":
            return ["metric-catalog#success_rate"]
        if tool_name == "query_metric":
            return ["warehouse#tenant-a"]
        return []
