from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


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


@dataclass(frozen=True)
class AgentExecution:
    messages: list[AgentMessage]
    handoffs: list[AgentHandoff] = field(default_factory=list)


@dataclass(frozen=True)
class OrchestrationResult:
    thread_key: str
    transcript: list[AgentMessage]
