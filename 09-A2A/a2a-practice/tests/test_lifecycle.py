import hashlib
import json

import pytest
from pydantic import ValidationError

from a2a_lab.lifecycle import LifecycleError, TaskLifecycleService, TaskRecord


def submit(service: TaskLifecycleService, key: str = "k1"):
    return service.submit(
        tenant="tenant-a",
        idempotency_key=key,
        summary={"revenue": 10},
        trace_id="trace-1",
    )


def test_state_machine_rejects_skipping_working_and_terminal_reentry():
    service = TaskLifecycleService()
    task = submit(service).task

    with pytest.raises(LifecycleError) as skipped:
        service.complete(task.id, "tenant-a", "report")
    assert skipped.value.code == "INVALID_STATE_TRANSITION"

    service.start(task.id, "tenant-a")
    service.complete(task.id, "tenant-a", "report")
    with pytest.raises(LifecycleError) as terminal:
        service.cancel(task.id, "tenant-a")
    assert terminal.value.code == "INVALID_STATE_TRANSITION"


def test_events_have_monotonic_sequence_and_do_not_copy_artifact_content():
    service = TaskLifecycleService()
    task = submit(service).task
    service.start(task.id, "tenant-a")
    service.complete(task.id, "tenant-a", "top secret report body")

    events = service.events(task.id, "tenant-a")

    assert [event.sequence for event in events] == [1, 2, 3]
    assert events[-1].details["artifact_bytes"] == len("top secret report body")
    assert "top secret report body" not in str(events)


def test_idempotency_is_scoped_by_tenant_and_payload():
    service = TaskLifecycleService()
    first = submit(service).task
    replay = submit(service).task

    assert first.id == replay.id
    with pytest.raises(LifecycleError) as conflict:
        service.submit(
            tenant="tenant-a",
            idempotency_key="k1",
            summary={"revenue": 11},
            trace_id="trace-2",
        )
    assert conflict.value.code == "IDEMPOTENCY_CONFLICT"


@pytest.mark.parametrize("invalid", [True, False, float("nan"), float("inf"), float("-inf")])
def test_domain_service_rejects_boolean_and_non_finite_aggregate_values(invalid):
    service = TaskLifecycleService()

    with pytest.raises(LifecycleError) as caught:
        service.submit(
            tenant="tenant-a",
            idempotency_key="bad-number",
            summary={"revenue": invalid},
            trace_id="trace-1",
        )

    assert caught.value.code == "SUMMARY_INVALID"
    assert service.tasks == {}


@pytest.mark.parametrize("invalid", [True, float("nan"), float("inf"), float("-inf")])
def test_task_record_itself_cannot_be_constructed_with_invalid_aggregate(invalid):
    with pytest.raises(ValidationError):
        TaskRecord(
            id="task-1",
            tenant="tenant-a",
            idempotency_key="key-1",
            payload_digest="unused",
            trace_id="trace-1",
            summary={"revenue": invalid},
            state="submitted",
            version=1,
        )


def test_summary_memory_json_and_digest_share_one_canonical_representation():
    service = TaskLifecycleService()
    first = service.submit(
        tenant="tenant-a",
        idempotency_key="canonical",
        summary={"z_rate": 1.0, "a_count": 2},
        trace_id="trace-1",
    ).task
    replay = service.submit(
        tenant="tenant-a",
        idempotency_key="canonical",
        summary={"a_count": 2, "z_rate": 1.0},
        trace_id="trace-2",
    ).task

    canonical = json.dumps(first.summary, sort_keys=True, separators=(",", ":"), allow_nan=False)
    assert list(first.summary) == ["a_count", "z_rate"]
    assert first.model_dump(mode="json")["summary"] == first.summary
    assert first.payload_digest == hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    assert replay.id == first.id
    with pytest.raises(TypeError, match="只读快照"):
        first.summary["a_count"] = 999
    assert first.payload_digest == hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def test_cross_tenant_read_is_indistinguishable_from_missing_task():
    service = TaskLifecycleService()
    task = submit(service).task

    with pytest.raises(LifecycleError) as caught:
        service.get(task.id, "tenant-b")

    assert caught.value.code == "TASK_NOT_FOUND"


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("tenant", "", "TENANT_INVALID"),
        ("tenant", "x" * 101, "TENANT_INVALID"),
        ("trace_id", None, "TRACE_ID_INVALID"),
        ("trace_id", "", "TRACE_ID_INVALID"),
        ("idempotency_key", 123, "IDEMPOTENCY_KEY_INVALID"),
    ],
)
def test_submission_identity_fields_fail_fast(field, value, code):
    service = TaskLifecycleService()
    kwargs = {
        "tenant": "tenant-a",
        "idempotency_key": "k1",
        "summary": {"revenue": 10},
        "trace_id": "trace-1",
    }
    kwargs[field] = value

    with pytest.raises(LifecycleError) as caught:
        service.submit(**kwargs)

    assert caught.value.code == code


@pytest.mark.parametrize("after", [-1, True, 1.5])
def test_event_cursor_fails_fast_when_not_a_nonnegative_integer(after):
    service = TaskLifecycleService()
    task = submit(service).task

    with pytest.raises(LifecycleError) as caught:
        service.events(task.id, "tenant-a", after=after)

    assert caught.value.code == "INVALID_CURSOR"
