import pytest

from a2a_lab.lifecycle import LifecycleError, TaskLifecycleService, TaskState, TERMINAL_STATES


def working():
    service = TaskLifecycleService()
    task = service.submit(tenant="a", idempotency_key="k", summary={"count": 2}, trace_id="trace").task
    service.start(task.id, "a")
    return service, task.id


def test_input_required_is_not_terminal_and_cannot_complete_without_resume():
    service, task_id = working()
    service.require_input(task_id, "a")
    assert TaskState.INPUT_REQUIRED not in TERMINAL_STATES
    with pytest.raises(LifecycleError):
        service.complete(task_id, "a", "premature")
    with pytest.raises(LifecycleError, match="输入"):
        service.resume(task_id, "a", input_text="")
    assert service.resume(task_id, "a", input_text="private input").state == TaskState.WORKING
    assert "private input" not in str(service.events(task_id, "a"))
    service.complete(task_id, "a", "done")


def test_auth_requires_trusted_checker_and_tenant_isolation():
    service, task_id = working()
    service.require_auth(task_id, "a")
    with pytest.raises(LifecycleError):
        service.start(task_id, "a")
    for kwargs in ({}, {"authorize": lambda _: False}):
        with pytest.raises(LifecycleError, match="授权"):
            service.resume(task_id, "a", **kwargs)
    with pytest.raises(LifecycleError, match="不存在"):
        service.resume(task_id, "b", authorize=lambda _: True)
    assert service.resume(task_id, "a", authorize=lambda task: task.tenant == "a").state == TaskState.WORKING


def test_canceled_waiting_task_cannot_resume():
    service, task_id = working()
    service.require_auth(task_id, "a")
    service.cancel(task_id, "a")
    with pytest.raises(LifecycleError):
        service.resume(task_id, "a", authorize=lambda _: True)
