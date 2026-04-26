from __future__ import annotations

from pixie_for_pm.domain.models import (
    AgentRole,
    DispatchRequest,
    IncomingDiscordMessage,
)


def build_dispatch_request(message: IncomingDiscordMessage) -> DispatchRequest:
    if message.is_reply_to_bot:
        reason = "reply_to_bot"
    elif message.directly_mentions_bot:
        reason = "direct_bot_mention"
    else:
        reason = "discord_message"

    return DispatchRequest(
        message=message,
        target_agent=AgentRole.PRODUCT_MANAGER,
        reason=reason,
    )
