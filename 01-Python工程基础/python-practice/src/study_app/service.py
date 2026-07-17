import json
import logging
from pathlib import Path

from pydantic import ValidationError

from study_app.schemas import StudyTask


logger = logging.getLogger(__name__)


class TaskStorageError(Exception):
    """任务文件保存或读取失败。"""


def calculate_total_hours(tasks: list[StudyTask]) -> float:
    """计算所有任务的预计总小时。"""
    total = sum(task.hours for task in tasks)
    logger.info("计算了 %d 个任务，总小时为 %.1f", len(tasks), total)
    return total


def save_tasks(tasks: list[StudyTask], path: str | Path) -> None:
    """将任务列表保存为 UTF-8 JSON 文件。"""
    file_path = Path(path)
    task_data = [task.model_dump() for task in tasks]

    try:
        file_path.write_text(
            json.dumps(task_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError as exc:
        logger.exception("保存任务失败：%s", file_path)
        raise TaskStorageError(f"保存任务失败：{file_path}") from exc

    logger.info("已保存 %d 个任务到 %s", len(tasks), file_path)


def load_tasks(path: str | Path) -> list[StudyTask]:
    """从 UTF-8 JSON 文件读取并校验任务列表。"""
    file_path = Path(path)

    try:
        text = file_path.read_text(encoding="utf-8")
        task_data = json.loads(text)
    except FileNotFoundError as exc:
        logger.error("任务文件不存在：%s", file_path)
        raise TaskStorageError(f"任务文件不存在：{file_path}") from exc
    except json.JSONDecodeError as exc:
        logger.error("任务文件不是合法 JSON：%s", file_path)
        raise TaskStorageError(f"任务文件不是合法 JSON：{file_path}") from exc
    except OSError as exc:
        logger.exception("读取任务失败：%s", file_path)
        raise TaskStorageError(f"读取任务失败：{file_path}") from exc

    if not isinstance(task_data, list):
        logger.error("任务文件顶层不是列表：%s", file_path)
        raise TaskStorageError("任务文件顶层必须是列表")

    try:
        tasks = [
            StudyTask.model_validate(item)
            for item in task_data
        ]
    except ValidationError as exc:
        logger.error("任务数据校验失败：%s", file_path)
        raise TaskStorageError(f"任务数据校验失败：{file_path}") from exc

    logger.info("从 %s 读取了 %d 个任务", file_path, len(tasks))
    return tasks