import logging

import pytest
from pydantic import ValidationError

from study_app.schemas import StudyTask
from study_app.service import (
    TaskStorageError,
    calculate_total_hours,
    load_tasks,
    save_tasks,
)


def test_study_task_validation() -> None:
    task = StudyTask(
        title="  学习 Python  ",
        priority=1,
        hours=2,
    )

    assert task.title == "学习 Python"
    assert task.completed is False

    with pytest.raises(ValidationError):
        StudyTask(
            title=" ",
            priority=4,
            hours=0,
        )


def test_calculate_total_hours(caplog: pytest.LogCaptureFixture) -> None:
    tasks = [
        StudyTask(title="Python", priority=1, hours=2),
        StudyTask(title="Pydantic", priority=2, hours=3.5),
    ]

    with caplog.at_level(logging.INFO):
        total = calculate_total_hours(tasks)

    assert total == 5.5
    assert "总小时" in caplog.text


def test_save_and_load_tasks(tmp_path) -> None:
    path = tmp_path / "tasks.json"
    original_tasks = [
        StudyTask(title="学习 Python", priority=1, hours=2),
        StudyTask(
            title="学习 pytest",
            priority=2,
            hours=3,
            completed=True,
        ),
    ]

    save_tasks(original_tasks, path)
    loaded_tasks = load_tasks(path)

    assert loaded_tasks == original_tasks
    assert "学习 Python" in path.read_text(encoding="utf-8")


def test_load_tasks_missing_file(tmp_path) -> None:
    missing_path = tmp_path / "missing.json"

    with pytest.raises(TaskStorageError, match="不存在"):
        load_tasks(missing_path)


def test_load_tasks_invalid_json(tmp_path) -> None:
    path = tmp_path / "invalid.json"
    path.write_text("{不是合法的 JSON", encoding="utf-8")

    with pytest.raises(TaskStorageError, match="合法 JSON"):
        load_tasks(path)