import httpx
import pytest
import pytest_asyncio

from a2a_lab.custom_http import build_custom_http_app
from a2a_lab.lifecycle import TaskLifecycleService


@pytest.fixture
def service() -> TaskLifecycleService:
    return TaskLifecycleService()


@pytest_asyncio.fixture
async def client(service):
    transport = httpx.ASGITransport(app=build_custom_http_app(service))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as value:
        yield value


def headers(*scopes: str, key: str = "idem-1", tenant: str = "tenant-a") -> dict[str, str]:
    return {
        "x-tenant": tenant,
        "x-scopes": " ".join(scopes),
        "idempotency-key": key,
    }


def body(revenue: int = 1) -> dict:
    return {"summary": {"revenue": revenue}, "trace_id": "trace-1"}


@pytest.mark.asyncio
async def test_private_agent_discovery_must_define_its_own_states_and_version(client):
    response = await client.get("/agents")
    agent = response.json()["agents"][0]
    assert agent["id"] == "report-agent"
    assert "working" in agent["task_states"]
    assert agent["version"] == "0.2.0"


@pytest.mark.asyncio
async def test_private_task_requires_scope_and_idempotency_key(client):
    no_scope = await client.post("/tasks", headers=headers(), json=body())
    no_key = await client.post(
        "/tasks",
        headers={"x-tenant": "tenant-a", "x-scopes": "report:create"},
        json=body(),
    )

    assert no_scope.status_code == 403
    assert no_key.status_code == 422
    assert no_key.json()["code"] == "IDEMPOTENCY_KEY_INVALID"


@pytest.mark.asyncio
async def test_private_task_advances_and_exposes_ordered_events(client):
    auth = headers("report:create", "report:execute")
    created = await client.post("/tasks", headers=auth, json=body())
    task_id = created.json()["id"]

    completed = await client.post(f"/tasks/{task_id}:run", headers=auth)
    events = await client.get(f"/tasks/{task_id}/events", headers=auth)

    assert completed.json()["state"] == "completed"
    assert completed.json()["artifact"].startswith("# 管理报告")
    event_list = events.json()["events"]
    assert [event["state"] for event in event_list] == ["submitted", "working", "completed"]
    assert [event["sequence"] for event in event_list] == [1, 2, 3]


@pytest.mark.asyncio
async def test_event_cursor_returns_only_newer_events(client):
    auth = headers("report:create", "report:execute")
    task_id = (await client.post("/tasks", headers=auth, json=body())).json()["id"]
    await client.post(f"/tasks/{task_id}:run", headers=auth)

    response = await client.get(f"/tasks/{task_id}/events?after=1", headers=auth)

    assert [event["sequence"] for event in response.json()["events"]] == [2, 3]

    invalid = await client.get(f"/tasks/{task_id}/events?after=-1", headers=auth)
    assert invalid.status_code == 422
    assert invalid.json()["code"] == "INVALID_CURSOR"


@pytest.mark.asyncio
async def test_create_is_idempotent_but_payload_conflict_is_rejected(client, service):
    auth = headers("report:create", key="stable-key")
    first = await client.post("/tasks", headers=auth, json=body(1))
    replay = await client.post("/tasks", headers=auth, json=body(1))
    conflict = await client.post("/tasks", headers=auth, json=body(2))

    assert first.status_code == 202
    assert replay.status_code == 200
    assert first.json()["id"] == replay.json()["id"]
    assert replay.headers["Idempotent-Replay"] == "true"
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "IDEMPOTENCY_CONFLICT"
    assert len(service.tasks) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "raw_summary",
    [
        '{"revenue":true}',
        '{"revenue":NaN}',
        '{"revenue":Infinity}',
        '{"revenue":-Infinity}',
        '{"revenue":"1"}',
    ],
)
async def test_http_rejects_boolean_and_non_finite_aggregate_values(client, service, raw_summary):
    # 用原始 JSON 覆盖非标准 NaN/Infinity token，确保异常在生成响应前被稳定映射为 422。
    response = await client.post(
        "/tasks",
        headers={**headers("report:create"), "content-type": "application/json"},
        content=f'{{"summary":{raw_summary},"trace_id":"trace-1"}}',
    )

    assert response.status_code == 422
    assert response.json()["code"] == "INVALID_REQUEST"
    assert service.tasks == {}


@pytest.mark.asyncio
async def test_private_task_can_cancel_only_before_terminal_state(client):
    auth = headers("report:create", "report:cancel")
    task_id = (await client.post("/tasks", headers=auth, json=body())).json()["id"]

    canceled = await client.post(f"/tasks/{task_id}:cancel", headers=auth)
    repeated = await client.post(f"/tasks/{task_id}:cancel", headers=auth)

    assert canceled.json()["state"] == "canceled"
    assert repeated.status_code == 409
    assert repeated.json()["code"] == "INVALID_STATE_TRANSITION"


@pytest.mark.asyncio
async def test_tenant_cannot_observe_another_tenants_task(client):
    owner = headers("report:create")
    task_id = (await client.post("/tasks", headers=owner, json=body())).json()["id"]

    response = await client.get(
        f"/tasks/{task_id}", headers=headers(tenant="tenant-b", key="unused")
    )

    assert response.status_code == 404
    assert response.json()["code"] == "TASK_NOT_FOUND"


@pytest.mark.asyncio
async def test_runner_exception_moves_task_to_failed_without_leaking_message(service):
    def broken_renderer(_summary):
        raise RuntimeError("database password was exposed")

    app = build_custom_http_app(service, broken_renderer)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as local_client:
        auth = headers("report:create", "report:execute")
        task_id = (await local_client.post("/tasks", headers=auth, json=body())).json()["id"]
        failed = await local_client.post(f"/tasks/{task_id}:run", headers=auth)

    assert failed.status_code == 500
    assert failed.json()["state"] == "failed"
    assert failed.json()["error_code"] == "REPORT_GENERATION_FAILED"
    assert "database password" not in failed.text
