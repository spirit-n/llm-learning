"""Provider-neutral accounting boundary; missing usage is unknown, never zero."""
from dataclasses import dataclass
from typing import Any, Protocol


class ModelResult(Protocol):
    usage: dict[str, Any] | None
    model: str | None
    response_id: str | None
    attempts: int


@dataclass(frozen=True)
class UsageReceipt:
    response_id: str | None
    model: str | None
    usage: dict[str, Any] | None
    attempts: int
    # Monetary cost requires a dated price table and provider billing semantics.
    cost_usd: float | None = None


def receipt_from_result(result: ModelResult) -> UsageReceipt:
    from copy import deepcopy
    return UsageReceipt(result.response_id, result.model, deepcopy(result.usage), result.attempts)
