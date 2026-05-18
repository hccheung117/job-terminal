from typing import TypeVar

from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


def openai(model: str) -> BaseChatModel:
    return ChatOpenAI(model=model)


def judge(model: BaseChatModel, prompt: str, schema: type[T]) -> T:
    result = model.with_structured_output(schema).invoke(prompt)
    if not isinstance(result, schema):
        raise RuntimeError(f"Unexpected structured output: {result!r}")
    return result
