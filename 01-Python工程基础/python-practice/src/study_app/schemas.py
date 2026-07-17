from pydantic import BaseModel, ConfigDict, Field


class StudyTask(BaseModel):
    """一项需要完成的学习任务。"""

    model_config = ConfigDict(str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=100)
    priority: int = Field(ge=0, le=3)
    hours: float = Field(gt=0, le=100)
    completed: bool = False