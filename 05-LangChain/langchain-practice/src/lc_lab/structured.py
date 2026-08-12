"""Prompt 模板和结构化输出。"""

from typing import Literal

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, ConfigDict, Field


class Intent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: Literal["knowledge", "data_query", "other"]
    reason: str = Field(min_length=1, max_length=200)
    confidence: float = Field(default=1.0, ge=0, le=1)
    requested_metric: str | None = None


class IntentParseResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool
    value: Intent | None = None
    error_code: Literal["INVALID_JSON", "SCHEMA_MISMATCH"] | None = None


parser = PydanticOutputParser(pydantic_object=Intent)
prompt = ChatPromptTemplate.from_messages(
    [
        ("system", "将问题分类。信息不足时选 other。\n{format_instructions}"),
        ("human", "{question}"),
    ]
).partial(format_instructions=parser.get_format_instructions())


def parse_intent(raw_model_text: str) -> Intent:
    return parser.parse(raw_model_text)


def safe_parse_intent(raw_model_text: str) -> IntentParseResult:
    """边界层保留结构化失败，不用正则“修好”一个语义可能错误的答案。"""
    try:
        return IntentParseResult(ok=True, value=parse_intent(raw_model_text))
    except Exception as exc:
        error_code = "INVALID_JSON" if "json" in str(exc).lower() else "SCHEMA_MISMATCH"
        return IntentParseResult(ok=False, error_code=error_code)
