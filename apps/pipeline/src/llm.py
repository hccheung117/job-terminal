import os
from typing import TypeVar

from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


def small() -> BaseChatModel:
    return chat(os.environ["SMALL_MODEL_NAME"], os.environ["SMALL_MODEL_PROVIDER"])


def chat(name: str, provider: str) -> BaseChatModel:
    match provider:
        case "openai":
            return ChatOpenAI(model=name)
        case "google" | "gemini":
            return ChatGoogleGenerativeAI(
                model=name,
                client_options={"api_endpoint": os.environ["GOOGLE_API_BASE"]},
            )
        case "anthropic":
            return ChatAnthropic(model=name)
        case _:
            raise ValueError(f"Unknown LLM provider: {provider!r}")


def judge(model: BaseChatModel, prompt: str, schema: type[T]) -> T:
    result = model.with_structured_output(schema).invoke(prompt)
    if not isinstance(result, schema):
        raise RuntimeError(f"Unexpected structured output: {result!r}")
    return result
