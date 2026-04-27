from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping

from pixie_for_pm.agents.dispatcher import build_dispatcher_handler
from pixie_for_pm.agents.product_manager import build_product_manager_handler
from pixie_for_pm.domain.models import (
    AgentExecution,
    AgentMessage,
    AgentRole,
    WorkflowContext,
)

AgentHandler = Callable[[WorkflowContext], Awaitable[AgentExecution]]


def _placeholder_message(role: AgentRole, user_message: str) -> str:
    return (
        f"E2E_PLACEHOLDER_OK [{role.label}] "
        "Discord -> LangGraph -> agent -> Discord loop is working. "
        f"Original message: {user_message}"
    )


def _build_placeholder_handler(role: AgentRole) -> AgentHandler:
    async def _handler(context: WorkflowContext) -> AgentExecution:
        return AgentExecution(
            messages=[
                AgentMessage(
                    agent=role,
                    content=_placeholder_message(
                        role=role, user_message=context.user_message
                    ),
                )
            ]
        )

    return _handler


def default_agent_handlers() -> dict[AgentRole, AgentHandler]:
    handlers = {role: _build_placeholder_handler(role) for role in AgentRole}
    handlers[AgentRole.DISPATCHER] = build_dispatcher_handler()
    return handlers


def resolve_agent_handlers(
    overrides: Mapping[AgentRole, AgentHandler] | None = None,
) -> dict[AgentRole, AgentHandler]:
    handlers = default_agent_handlers()
    if overrides is not None:
        handlers.update(overrides)
    return handlers


__all__ = [
    "AgentHandler",
    "build_dispatcher_handler",
    "build_product_manager_handler",
    "default_agent_handlers",
    "resolve_agent_handlers",
]
