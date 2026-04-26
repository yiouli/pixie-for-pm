from __future__ import annotations

from pixie_for_pm.domain.models import (
    AgentRole,
    DispatchRequest,
    IncomingDiscordMessage,
)


def build_dispatch_request(message: IncomingDiscordMessage) -> DispatchRequest:
    if message.mentioned_agents:
        return DispatchRequest(
            message=message,
            target_agent=message.mentioned_agents[0],
            reason="mentioned_agent",
        )

    if message.reply_to_agent is not None:
        return DispatchRequest(
            message=message,
            target_agent=message.reply_to_agent,
            reason="reply_to_agent",
        )

    return DispatchRequest(
        message=message,
        target_agent=AgentRole.PRODUCT_MANAGER,
        reason="default_product_manager",
    )
