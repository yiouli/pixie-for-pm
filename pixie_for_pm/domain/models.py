from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pixie_for_pm.integrations.toolset import AgentToolset, DiscordTriggerContext


StatusEmitter = Callable[[str], Awaitable[None] | None]
ResponseEmitter = Callable[[str], Awaitable[None] | None]


async def emit_status_update(
    status_emitter: StatusEmitter | None,
    status: str,
) -> None:
    if status_emitter is None:
        return

    maybe_awaitable = status_emitter(status)
    if inspect.isawaitable(maybe_awaitable):
        await maybe_awaitable


async def emit_response_chunk(
    response_emitter: ResponseEmitter | None,
    chunk: str,
) -> None:
    if response_emitter is None or chunk == "":
        return

    maybe_awaitable = response_emitter(chunk)
    if inspect.isawaitable(maybe_awaitable):
        await maybe_awaitable


class AgentRole(StrEnum):
    PRODUCT_MANAGER = "product_manager"
    MARKET_ANALYST = "market_analyst"
    USER_RESEARCHER = "user_researcher"
    DATA_SCIENTIST = "data_scientist"
    PRODUCT_DESIGNER = "product_designer"

    @property
    def label(self) -> str:
        return self.value.replace("_", " ")


@dataclass(frozen=True)
class IncomingDiscordMessage:
    discord_message_id: int
    discord_server_id: str
    channel_id: int
    thread_id: str | None
    author_id: int
    content: str
    directly_mentions_bot: bool
    is_reply_to_bot: bool


@dataclass(frozen=True)
class DispatchRequest:
    message: IncomingDiscordMessage
    target_agent: AgentRole
    reason: str

    @property
    def thread_key(self) -> str:
        if self.message.thread_id is not None:
            return self.message.thread_id
        return f"channel-{self.message.channel_id}-message-{self.message.discord_message_id}"


@dataclass(frozen=True)
class AgentMessage:
    agent: AgentRole
    content: str


@dataclass(frozen=True)
class AgentHandoff:
    source_agent: AgentRole
    target_agent: AgentRole
    reason: str


@dataclass(frozen=True)
class WorkflowContext:
    thread_key: str
    current_agent: AgentRole
    user_message: str
    transcript: tuple[AgentMessage, ...]
    trigger: DiscordTriggerContext
    toolset: AgentToolset
    status_emitter: StatusEmitter | None = None
    response_emitter: ResponseEmitter | None = None


@dataclass(frozen=True)
class AgentExecution:
    messages: list[AgentMessage]
    handoffs: list[AgentHandoff] = field(default_factory=list)


@dataclass(frozen=True)
class OrchestrationResult:
    thread_key: str
    transcript: list[AgentMessage]
