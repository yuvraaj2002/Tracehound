"""Structured output from a local Ollama model."""

from typing import Protocol, TypeVar

import httpx
import ollama
from pydantic import BaseModel, ValidationError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

T = TypeVar("T", bound=BaseModel)

RETRYABLE = (ollama.ResponseError, ConnectionError, httpx.HTTPError, ValidationError)
"""Server errors, connection failures, and output that doesn't match the schema."""


class LLMError(RuntimeError):
    """The model gave no usable structured output after all retries."""


class StructuredLLM(Protocol):
    def generate(self, *, system: str, user: str, schema: type[T]) -> T: ...


class OllamaLLM:
    def __init__(self, model: str = "lfm2.5-thinking") -> None:
        self.model = model

    def generate(self, *, system: str, user: str, schema: type[T]) -> T:
        try:
            return self._chat(system, user, schema)
        except RETRYABLE as exc:
            raise LLMError(f"{self.model} failed after retries: {exc}") from exc

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=1, max=10),
        retry=retry_if_exception_type(RETRYABLE),
        reraise=True,
    )
    def _chat(self, system: str, user: str, schema: type[T]) -> T:
        response = ollama.chat(
            model=self.model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            format=schema.model_json_schema(),
        )
        return schema.model_validate_json(response.message.content)
