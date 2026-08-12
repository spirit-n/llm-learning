import asyncio
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio

from a2a_lab.a2a_server import a2a_app, build_a2a_app
from a2a_lab.execution import ReportExecutionLedger


pytestmark = pytest.mark.filterwarnings(
    r"ignore:label\(\) is deprecated.*:DeprecationWarning:a2a\.utils\.proto_utils"
)


@pytest_asyncio.fixture
async def client():
    transport = httpx.ASGITransport(app=a2a_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as value:
        yield value


def message_body(
    text: str,
    tenant: str = "tenant-a",
    *,
    idempotency_key: str | None = None,
    return_immediately: bool = False,
) -> dict:
    metadata = {"traceId": "trace-test"}
    if idempotency_key:
        metadata["idempotencyKey"] = idempotency_key
    return {
        "tenant": tenant,
        "message": {"messageId": uuid4().hex, "role": "ROLE_USER", "parts": [{"text": text}]},
        "configuration": {"returnImmediately": return_immediately},
        "metadata": metadata,
    }


@pytest.mark.asyncio
async def test_agent_card_declares_skill_and_interface(client):
    response = await client.get("/.well-known/agent-card.json")
    card = response.json()
    assert card["skills"][0]["id"] == "generate-management-report"
    assert card["supportedInterfaces"][0]["protocolVersion"] == "1.0"


@pytest.mark.asyncio
async def test_version_header_is_required(client):
    response = await client.post("/a2a/message:send", json=message_body("revenue=1"))
    assert response.status_code == 400
    assert "version" in response.text.lower()


@pytest.mark.asyncio
async def test_a2a_task_completes_with_artifact(client):
    response = await client.post(
        "/a2a/message:send",
        headers={"A2A-Version": "1.0", "X-Tenant": "tenant-a"},
        json=message_body("收入 128000，成功率 98%，仅聚合数据。"),
    )
    assert response.status_code == 200, response.text
    task = response.json()["task"]
    assert task["status"]["state"] == "TASK_STATE_COMPLETED"
    assert task["artifacts"][0]["name"] == "management-report.md"
    assert "管理报告" in task["artifacts"][0]["parts"][0]["text"]
    assert task["artifacts"][0]["metadata"]["trace_id"] == "trace-test"


@pytest.mark.asyncio
async def test_report_generator_can_be_injected_without_changing_protocol_boundary():
    async def custom_generator(summary: str) -> str:
        return f"# injected\n\n{summary}"

    transport = httpx.ASGITransport(app=build_a2a_app(custom_generator))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as local_client:
        response = await local_client.post(
            "/a2a/message:send",
            headers={"A2A-Version": "1.0", "X-Tenant": "tenant-a"},
            json=message_body("收入 128000，仅聚合数据。"),
        )
    artifact = response.json()["task"]["artifacts"][0]
    assert artifact["parts"][0]["text"].startswith("# injected")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "sensitive_text",
    [
        "客户邮箱 alice@example.com，生成报告",
        "Authorization: Bearer abc.def_123，生成报告",
        "api_key=abcdefghijk12345，生成报告",
        "密钥 sk-abcdefghijklmnopqrstuvwxyz，生成报告",
    ],
)
async def test_sensitive_detail_is_rejected(client, sensitive_text):
    response = await client.post(
        "/a2a/message:send",
        headers={"A2A-Version": "1.0", "X-Tenant": "tenant-a"},
        json=message_body(sensitive_text),
    )
    task = response.json()["task"]
    assert task["status"]["state"] == "TASK_STATE_REJECTED"
    assert "artifacts" not in task


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("traceId", None),
        ("traceId", 123),
        ("idempotencyKey", ""),
        ("idempotencyKey", "x" * 101),
    ],
)
async def test_untrusted_metadata_must_be_bounded_nonempty_strings(client, field, value):
    payload = message_body("收入 1，仅聚合数据。")
    payload["metadata"][field] = value

    response = await client.post(
        "/a2a/message:send",
        headers={"A2A-Version": "1.0", "X-Tenant": "tenant-a"},
        json=payload,
    )

    task = response.json()["task"]
    assert task["status"]["state"] == "TASK_STATE_REJECTED"
    assert "INVALID_METADATA" in task["status"]["message"]["parts"][0]["text"]


@pytest.mark.asyncio
async def test_unauthorized_tenant_is_rejected(client):
    response = await client.post(
        "/a2a/message:send",
        headers={"A2A-Version": "1.0", "X-Tenant": "tenant-b"},
        json=message_body("收入 1", tenant="tenant-b"),
    )
    assert response.json()["task"]["status"]["state"] == "TASK_STATE_REJECTED"


@pytest.mark.asyncio
async def test_gateway_tenant_wins_over_untrusted_body_tenant(client):
    response = await client.post(
        "/a2a/message:send",
        headers={"A2A-Version": "1.0", "X-Tenant": "tenant-a"},
        json=message_body("收入 1，仅聚合数据。", tenant="tenant-b"),
    )

    assert response.json()["task"]["status"]["state"] == "TASK_STATE_COMPLETED"


@pytest.mark.asyncio
async def test_a2a_idempotency_replays_artifact_without_running_generator_twice():
    calls = 0

    async def counting_generator(summary: str) -> str:
        nonlocal calls
        calls += 1
        return f"# report\n\n{summary}"

    ledger = ReportExecutionLedger()
    app = build_a2a_app(counting_generator, ledger=ledger)
    transport = httpx.ASGITransport(app=app)
    headers = {"A2A-Version": "1.0", "X-Tenant": "tenant-a"}
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as local_client:
        first = await local_client.post(
            "/a2a/message:send",
            headers=headers,
            json=message_body("收入 1，仅聚合数据。", idempotency_key="stable-key"),
        )
        replay = await local_client.post(
            "/a2a/message:send",
            headers=headers,
            json=message_body("收入 1，仅聚合数据。", idempotency_key="stable-key"),
        )

    assert first.json()["task"]["status"]["state"] == "TASK_STATE_COMPLETED"
    replay_task = replay.json()["task"]
    assert replay_task["status"]["state"] == "TASK_STATE_COMPLETED"
    assert replay_task["artifacts"][0]["metadata"]["replayed"] is True
    assert calls == 1
    assert [event["event_type"] for event in ledger.events][-1] == "execution_replayed"


@pytest.mark.asyncio
async def test_a2a_idempotency_conflict_is_rejected():
    app = build_a2a_app()
    transport = httpx.ASGITransport(app=app)
    headers = {"A2A-Version": "1.0", "X-Tenant": "tenant-a"}
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as local_client:
        await local_client.post(
            "/a2a/message:send",
            headers=headers,
            json=message_body("收入 1，仅聚合数据。", idempotency_key="conflict-key"),
        )
        conflict = await local_client.post(
            "/a2a/message:send",
            headers=headers,
            json=message_body("收入 2，仅聚合数据。", idempotency_key="conflict-key"),
        )

    task = conflict.json()["task"]
    assert task["status"]["state"] == "TASK_STATE_REJECTED"
    assert "IDEMPOTENCY_CONFLICT" in task["status"]["message"]["parts"][0]["text"]


@pytest.mark.asyncio
async def test_generator_failure_becomes_failed_task_and_sanitized_event():
    async def broken_generator(_summary: str) -> str:
        raise RuntimeError("provider key leaked here")

    ledger = ReportExecutionLedger()
    app = build_a2a_app(broken_generator, ledger=ledger)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as local_client:
        response = await local_client.post(
            "/a2a/message:send",
            headers={"A2A-Version": "1.0", "X-Tenant": "tenant-a"},
            json=message_body("收入 1，仅聚合数据。"),
        )

    task = response.json()["task"]
    assert task["status"]["state"] == "TASK_STATE_FAILED"
    assert "provider key" not in response.text
    assert ledger.events[-1]["error_code"] == "GENERATION_FAILED"


@pytest.mark.asyncio
async def test_generator_timeout_is_a_terminal_failed_state():
    async def slow_generator(_summary: str) -> str:
        await asyncio.sleep(0.05)
        return "late"

    app = build_a2a_app(slow_generator, generation_timeout_seconds=0.01)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as local_client:
        response = await local_client.post(
            "/a2a/message:send",
            headers={"A2A-Version": "1.0", "X-Tenant": "tenant-a"},
            json=message_body("收入 1，仅聚合数据。"),
        )

    assert response.json()["task"]["status"]["state"] == "TASK_STATE_FAILED"


@pytest.mark.asyncio
async def test_cancel_while_working_wins_over_late_generation_and_keeps_idempotency_terminal():
    started = asyncio.Event()
    release = asyncio.Event()
    calls = 0

    async def controlled_generator(_summary: str) -> str:
        nonlocal calls
        calls += 1
        started.set()
        await release.wait()
        return "# too late"

    ledger = ReportExecutionLedger()
    app = build_a2a_app(controlled_generator, ledger=ledger)
    transport = httpx.ASGITransport(app=app)
    headers = {"A2A-Version": "1.0", "X-Tenant": "tenant-a"}
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as local_client:
        submitted = await local_client.post(
            "/a2a/message:send",
            headers=headers,
            json=message_body(
                "收入 1，仅聚合数据。",
                idempotency_key="cancel-working",
                return_immediately=True,
            ),
        )
        task_id = submitted.json()["task"]["id"]
        await asyncio.wait_for(started.wait(), timeout=1)

        canceled = await local_client.post(
            f"/a2a/tasks/{task_id}:cancel", headers=headers, json={}
        )
        release.set()
        await asyncio.sleep(0.05)
        snapshot = await local_client.get(f"/a2a/tasks/{task_id}", headers=headers)
        replay = await local_client.post(
            "/a2a/message:send",
            headers=headers,
            json=message_body(
                "收入 1，仅聚合数据。", idempotency_key="cancel-working"
            ),
        )

    assert canceled.json()["status"]["state"] == "TASK_STATE_CANCELED"
    assert snapshot.json()["status"]["state"] == "TASK_STATE_CANCELED"
    assert next(iter(ledger.records.values())).state == "canceled"
    assert "execution_completed" not in [event["event_type"] for event in ledger.events]
    assert replay.json()["task"]["status"]["state"] == "TASK_STATE_REJECTED"
    assert "canceled" in replay.text
    assert calls == 1


@pytest.mark.parametrize("timeout", [0, -1, float("inf")])
def test_invalid_generation_timeout_fails_fast(timeout):
    with pytest.raises(ValueError):
        build_a2a_app(generation_timeout_seconds=timeout)
