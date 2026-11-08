"""Provider interface. Gemini is the only real provider today; others can implement the same two methods."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


class ProviderError(RuntimeError):
    """A failed LLM call, with a message that is safe to show to the user.

    kind: auth | quota | model | network | server | other. auth, quota and model errors pause the whole queue,
    since every other episode would fail the same way until the user changes settings.
    """

    def __init__(self, message: str, kind: str = "other"):
        super().__init__(message)
        self.kind = kind

    @property
    def pauses_queue(self) -> bool:
        return self.kind in ("auth", "quota", "model")


@dataclass
class LLMResult:
    data: dict
    raw_text: str
    usage: dict = field(default_factory=dict)
    model_version: str | None = None


class LLMProvider(Protocol):
    name: str

    def generate_json(
        self,
        *,
        model: str,
        system: str,
        messages: list[tuple[str, str]],
        schema: dict,
        thinking_level: str | None = None,
    ) -> LLMResult:
        """Run a structured-output call. messages are (role, text) with role 'user' or 'model'."""
        ...

    def list_models(self) -> list[str]:
        """Model ids this credential can call."""
        ...

    def close(self) -> None:
        ...
