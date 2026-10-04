"""Optional live spans. Importing the module never initializes a network exporter."""
from __future__ import annotations

import json
from contextlib import contextmanager
from typing import Any

from .tracing import redact

# Versioned local mapping, NOT a claim that evolving upstream GenAI is stable.
MAPPING_PROFILE = "eval-lab/genai-development/2026-10-04-v1"


class OTelAdapter:
    def __init__(self, provider):
        self.provider = provider
        self.tracer = provider.get_tracer("eval_lab", "0.1.0")

    @contextmanager
    def span(self, name: str, *, carrier: dict[str, str] | None = None, **attributes: Any):
        from opentelemetry.trace import Status, StatusCode
        from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
        context = TraceContextTextMapPropagator().extract(carrier) if carrier is not None else None
        cleaned = redact(attributes)
        safe = {key: value if isinstance(value, (str, bool, int, float)) else json.dumps(value, ensure_ascii=False)
                for key, value in cleaned.items() if value is not None}
        safe["lab.mapping_profile"] = MAPPING_PROFILE
        # Never auto-record exception messages/stack traces; they may contain credentials.
        with self.tracer.start_as_current_span(redact(name), context=context, attributes=safe,
                                               record_exception=False, set_status_on_exception=False) as span:
            try:
                yield span
            except Exception as exc:
                span.set_attribute("error.type", type(exc).__name__)
                span.set_status(Status(StatusCode.ERROR))
                raise

    @staticmethod
    def inject_context() -> dict[str, str]:
        from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
        carrier: dict[str, str] = {}
        TraceContextTextMapPropagator().inject(carrier)
        return carrier

    def close(self) -> None:
        self.provider.shutdown()


def make_otlp_adapter(endpoint: str) -> OTelAdapter:
    """Explicit opt-in. Caller chooses endpoint; no implicit env/config discovery."""
    from urllib.parse import urlparse
    parsed = urlparse(endpoint)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("必须提供无内嵌凭据的 HTTP(S) OTLP endpoint")
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    provider = TracerProvider()
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, timeout=3)))
    return OTelAdapter(provider)
