import json
from concurrent.futures import ThreadPoolExecutor

import pytest

pytest.importorskip("opentelemetry.sdk")
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from eval_lab.otel_adapter import OTelAdapter, MAPPING_PROFILE


def test_context_crosses_tool_thread_and_all_exported_data_is_redacted():
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    adapter = OTelAdapter(provider)
    secret = "sk-never-export-123456789"
    def tool(carrier):
        with adapter.span("execute_tool lookup", carrier=carrier, api_key=secret,
                          arguments={"password": secret}, note=f"Bearer {secret}"):
            raise RuntimeError(secret)
    try:
        with adapter.span("agent.run"):
            carrier = adapter.inject_context()
            assert "traceparent" in carrier and "baggage" not in carrier
            with ThreadPoolExecutor(max_workers=1) as pool:
                with pytest.raises(RuntimeError):
                    pool.submit(tool, carrier).result()
        spans = exporter.get_finished_spans()
        root = next(s for s in spans if s.name == "agent.run")
        child = next(s for s in spans if s.name.startswith("execute_tool"))
        assert child.context.trace_id == root.context.trace_id
        assert child.parent.span_id == root.context.span_id
        assert child.attributes["lab.mapping_profile"] == MAPPING_PROFILE
        assert child.attributes["error.type"] == "RuntimeError"
        assert not child.events
        assert secret not in json.dumps([dict(s.attributes) for s in spans])
    finally:
        adapter.close()
