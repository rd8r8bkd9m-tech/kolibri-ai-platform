from __future__ import annotations

import json
from typing import Any, Annotated, Literal, TypeAlias

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

from ..schemas import AGENT_PROFILE_ID_PATTERN


OpaqueClientId = Annotated[
    str,
    StringConstraints(
        strict=True,
        min_length=8,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._~-]{7,127}$",
    ),
]
AgentProfile: TypeAlias = Annotated[
    str,
    StringConstraints(
        strict=True,
        min_length=2,
        max_length=96,
        pattern=AGENT_PROFILE_ID_PATTERN,
    ),
]
ExecutionMode = Literal["standard", "developer"]
AccessMode = Literal["standard", "auto", "full"]


class StrictModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        populate_by_name=True,
    )


class TextPart(StrictModel):
    type: Literal["text"]
    text: str = Field(strict=True, min_length=1, max_length=65_536)


class AttachmentUrlSource(StrictModel):
    type: Literal["url"]
    value: str = Field(
        strict=True,
        min_length=48,
        max_length=240,
        pattern=(
            r"^/api/product/v1/attachments/"
            r"attachment_[A-Za-z0-9][A-Za-z0-9._~-]{5,127}/content$"
        ),
    )
    mime_type: str = Field(
        strict=True,
        min_length=3,
        max_length=160,
        alias="mimeType",
    )


class AttachmentMetadata(StrictModel):
    filename: str = Field(strict=True, min_length=1, max_length=240)


class AttachmentInputPart(StrictModel):
    type: Literal["image", "document"]
    source: AttachmentUrlSource
    metadata: AttachmentMetadata


class UserMessage(StrictModel):
    id: OpaqueClientId
    role: Literal["user"]
    content: str | list[TextPart | AttachmentInputPart]

    @model_validator(mode="after")
    def validate_content(self) -> UserMessage:
        if isinstance(self.content, str):
            if not self.content.strip() or len(self.content) > 65_536:
                raise ValueError("user content must contain bounded text")
            return self
        if not 1 <= len(self.content) <= 64:
            raise ValueError("user content must contain 1 to 64 parts")
        combined = message_text(self)
        if not combined.strip() or len(combined) > 65_536:
            raise ValueError("user content must contain text")
        attachments = [
            part for part in self.content
            if isinstance(part, AttachmentInputPart)
        ]
        if len(attachments) > 10:
            raise ValueError("a user message accepts at most 10 attachments")
        if len({part.source.value for part in attachments}) != len(attachments):
            raise ValueError("attachment references must be unique")
        return self


class AssistantFunctionCall(StrictModel):
    name: str = Field(strict=True, min_length=1, max_length=96)
    arguments: str = Field(strict=True, min_length=2, max_length=100_000)

    @model_validator(mode="after")
    def validate_arguments(self) -> "AssistantFunctionCall":
        try:
            value = json.loads(self.arguments)
        except (TypeError, ValueError):
            raise ValueError("tool arguments must be valid JSON") from None
        if not isinstance(value, dict):
            raise ValueError("tool arguments must be a JSON object")
        return self


class AssistantToolCall(StrictModel):
    id: OpaqueClientId
    type: Literal["function"]
    function: AssistantFunctionCall


class AssistantMessage(StrictModel):
    id: OpaqueClientId
    role: Literal["assistant"]
    content: str | list[TextPart] = ""
    tool_calls: list[AssistantToolCall] = Field(
        default_factory=list,
        max_length=32,
        alias="toolCalls",
    )

    @model_validator(mode="after")
    def validate_content(self) -> AssistantMessage:
        if isinstance(self.content, str):
            if len(self.content) > 200_000:
                raise ValueError("assistant content must contain bounded text")
        elif not 1 <= len(self.content) <= 64:
            raise ValueError("assistant content must contain 1 to 64 text parts")
        combined = message_text(self)
        if len(combined) > 200_000:
            raise ValueError("assistant content must contain text")
        if not combined.strip() and not self.tool_calls:
            raise ValueError("assistant content or tool calls are required")
        if len({call.id for call in self.tool_calls}) != len(self.tool_calls):
            raise ValueError("assistant tool call IDs must be unique")
        return self


AgUiMessage = Annotated[
    UserMessage | AssistantMessage,
    Field(discriminator="role"),
]


class ForwardedProps(StrictModel):
    agent_profile: AgentProfile | None = Field(
        default=None,
        alias="agentProfile",
    )
    execution_mode: ExecutionMode = Field(
        default="standard",
        alias="executionMode",
    )
    access_mode: AccessMode = Field(
        default="standard",
        alias="accessMode",
    )

    @model_validator(mode="after")
    def validate_access_mode(self) -> "ForwardedProps":
        access_was_explicit = "access_mode" in self.model_fields_set
        if not access_was_explicit and self.execution_mode == "developer":
            # Compatibility with the pre-accessMode v1 client. The parsed
            # value is structural only: accept_run detects the omitted field,
            # freezes the historical policy as version 1, and refuses to
            # execute it under broader v2 semantics. Keep the field out of
            # canonical hashing so an old exact retry stays idempotent.
            object.__setattr__(self, "access_mode", "auto")
        if (
            self.execution_mode == "standard"
            and self.access_mode != "standard"
        ):
            raise ValueError(
                "standard execution requires standard access"
            )
        if (
            self.execution_mode == "developer"
            and self.access_mode not in {"auto", "full"}
        ):
            raise ValueError(
                "developer execution requires auto or full access"
            )
        return self


class AgUiRunInput(StrictModel):
    thread_id: OpaqueClientId = Field(alias="threadId")
    run_id: OpaqueClientId = Field(alias="runId")
    state: None
    messages: list[AgUiMessage] = Field(min_length=1, max_length=200)
    tools: list[Any] = Field(max_length=0)
    context: list[Any] = Field(max_length=0)
    forwarded_props: ForwardedProps = Field(alias="forwardedProps")

    @model_validator(mode="after")
    def validate_run(self) -> AgUiRunInput:
        if self.messages[-1].role != "user":
            raise ValueError("the final message must be a user message")
        message_ids = [message.id for message in self.messages]
        if len(message_ids) != len(set(message_ids)):
            raise ValueError("message IDs must be unique")
        return self


class ThreadActionInput(StrictModel):
    action: Literal["archive", "unarchive", "pin", "unpin", "remove"]


class MessageFeedbackInput(StrictModel):
    type: Literal["positive", "negative"]


def message_text(message: AgUiMessage) -> str:
    if isinstance(message.content, str):
        return message.content
    return "".join(
        part.text for part in message.content
        if isinstance(part, TextPart)
    )


def message_attachment_parts(
    message: AgUiMessage,
) -> list[AttachmentInputPart]:
    if not isinstance(message, UserMessage) or isinstance(message.content, str):
        return []
    return [
        part for part in message.content
        if isinstance(part, AttachmentInputPart)
    ]


def canonical_run_payload(run_input: AgUiRunInput) -> dict[str, Any]:
    payload = run_input.model_dump(mode="json", by_alias=True)
    access_was_omitted = (
        "access_mode" not in run_input.forwarded_props.model_fields_set
    )
    explicit_standard_access = (
        run_input.forwarded_props.execution_mode == "standard"
        and run_input.forwarded_props.access_mode == "standard"
    )
    if access_was_omitted or explicit_standard_access:
        forwarded_props = payload.get("forwardedProps")
        if isinstance(forwarded_props, dict):
            forwarded_props.pop("accessMode", None)
    return payload
