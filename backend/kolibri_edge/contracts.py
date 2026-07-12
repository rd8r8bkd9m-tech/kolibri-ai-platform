from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class InputPart(StrictModel):
    type: Literal["input_text", "text"] = "input_text"
    text: str = Field(min_length=1, max_length=200_000)


class PublicInputMessage(StrictModel):
    """A public browser may add user input, never assistant output."""

    role: Literal["user"]
    content: str | list[InputPart]

    @model_validator(mode="after")
    def content_is_not_empty(self) -> "PublicInputMessage":
        if isinstance(self.content, str):
            text = self.content
        else:
            text = "".join(part.text for part in self.content)
        if not text.strip():
            raise ValueError("message content must contain text")
        return self


class ResponseCreate(BaseModel):
    """Supported public Responses request plus Kolibri project binding.

    Additive OpenAI fields are accepted and forwarded to Core, while the
    security-sensitive product identity and public author roles are strict.
    """

    model_config = ConfigDict(extra="allow", str_strip_whitespace=True)

    model: str = "kolibri"
    input: str | list[PublicInputMessage]
    instructions: str | None = Field(default=None, max_length=100_000)
    stream: bool = False
    background: bool = False
    project_id: str | None = Field(default=None, min_length=3, max_length=160)
    previous_response_id: str | None = Field(default=None, min_length=3, max_length=160)
    execution_mode: Literal["fast", "deep"] = "fast"
    reasoning: dict[str, Any] = Field(default_factory=dict)
    tools: list[dict[str, Any]] = Field(default_factory=list, max_length=64)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("model")
    @classmethod
    def public_model_only(cls, value: str) -> str:
        if value != "kolibri":
            raise ValueError("the public model is kolibri")
        return value

    @model_validator(mode="after")
    def input_is_not_empty(self) -> "ResponseCreate":
        if isinstance(self.input, str):
            text = self.input
        else:
            pieces: list[str] = []
            for message in self.input:
                if isinstance(message.content, str):
                    pieces.append(message.content)
                else:
                    pieces.extend(part.text for part in message.content)
            text = "".join(pieces)
        if not text.strip():
            raise ValueError("input must contain text")
        return self


IDEMPOTENCY_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{7,199}$")


def validate_idempotency_key(value: str | None) -> str:
    key = str(value or "").strip()
    if not key:
        raise ValueError("idempotency_key_required")
    if not IDEMPOTENCY_KEY.fullmatch(key):
        raise ValueError("invalid_idempotency_key")
    return key
