"""Model access behind one small interface, so agents and tests don't depend on a provider."""

from typing import Protocol, TypeVar

import anthropic
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

DEFAULT_MODEL = "claude-opus-5-5"


class LLMError(RuntimeError):
    """The model returned no usable structured output."""


class StructuredLLM(Protocol):
    def generate(self, *, system: str, user: str, schema: type[T]) -> T: ...


class AnthropicLLM:
    """Claude via the Anthropic SDK, returning a validated Pydantic object."""

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        effort: str = "low",
        max_tokens: int = 16000,
        client: anthropic.Anthropic | None = None,
    ) -> None:
        self.model = model
        self.effort = effort
        self.max_tokens = max_tokens
        self._client = client or anthropic.Anthropic()

    def generate(self, *, system: str, user: str, schema: type[T]) -> T:
        try:
            response = self._client.beta.messages.parse(
                model=self.model,
                max_tokens=self.max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
                output_format=schema,
                output_config={"effort": self.effort},
                # On a safety decline, the API retries on its recommended fallback model.
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
        except anthropic.APIError as exc:  # the SDK has already retried transient errors
            raise LLMError(f"{type(exc).__name__}: {exc}") from exc
        if response.stop_reason == "refusal":
            raise LLMError(f"model refused (request {response._request_id})")
        if response.parsed_output is None:
            raise LLMError(f"no structured output, stop_reason={response.stop_reason}")
        return response.parsed_output
