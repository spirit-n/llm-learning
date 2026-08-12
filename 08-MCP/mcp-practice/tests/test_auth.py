import pytest

import mcp_lab.auth as auth_module
from mcp_lab.auth import AuthenticationError, SignedRequestContext
from mcp_lab.models import Principal


def principal() -> Principal:
    return Principal(
        actor_id="gateway-user",
        tenant="tenant-a",
        scopes=frozenset({"query:execute"}),
    )


def test_signed_context_round_trip_preserves_authenticated_principal() -> None:
    gateway = SignedRequestContext("a-secure-test-secret-with-32-bytes-minimum")
    assert gateway.verify(gateway.issue(principal())) == principal()


def test_payload_or_signature_tampering_is_rejected() -> None:
    gateway = SignedRequestContext("a-secure-test-secret-with-32-bytes-minimum")
    token = gateway.issue(principal())
    with pytest.raises(AuthenticationError):
        gateway.verify(token[:-1] + ("A" if token[-1] != "A" else "B"))


def test_expired_context_is_rejected(monkeypatch) -> None:
    gateway = SignedRequestContext("a-secure-test-secret-with-32-bytes-minimum")
    monkeypatch.setattr(auth_module.time, "time", lambda: 1_000.0)
    token = gateway.issue(principal(), ttl_seconds=1)
    monkeypatch.setattr(auth_module.time, "time", lambda: 1_002.0)
    with pytest.raises(AuthenticationError, match="过期"):
        gateway.verify(token)
