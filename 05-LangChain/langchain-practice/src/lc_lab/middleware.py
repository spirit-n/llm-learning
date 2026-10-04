"""An actual create_agent middleware hook; authorization remains inside tools."""

from langchain.agents.middleware import wrap_tool_call


def tool_audit_middleware(events: list[dict[str, str]]):
    @wrap_tool_call
    def audit(request, handler):
        # Deliberately omit arguments/results: they may contain sensitive data.
        name = request.tool_call["name"]
        events.append({"tool": name, "stage": "started"})
        try:
            result = handler(request)
        except Exception:
            events.append({"tool": name, "stage": "failed"})
            raise
        events.append({"tool": name, "stage": "completed"})
        return result
    return audit
