from pixie_for_pm.discord.bot import should_dispatch_message
from pixie_for_pm.domain.models import AgentRole, IncomingDiscordMessage


def _message(
    *,
    content: str,
    mentioned_agents: tuple[AgentRole, ...] = (),
    reply_to_agent: AgentRole | None = None,
) -> IncomingDiscordMessage:
    return IncomingDiscordMessage(
        discord_message_id=1,
        channel_id=2,
        thread_id=None,
        author_id=3,
        content=content,
        mentioned_agents=mentioned_agents,
        reply_to_agent=reply_to_agent,
    )


def test_dispatches_when_specific_agent_token_is_present() -> None:
    message = _message(
        content="@market can you size this?",
        mentioned_agents=(AgentRole.MARKET_ANALYST,),
    )

    assert should_dispatch_message(message, bot_user_id=999) is True


def test_dispatches_when_replying_to_agent_message() -> None:
    message = _message(
        content="Can you continue that analysis?",
        reply_to_agent=AgentRole.PRODUCT_MANAGER,
    )

    assert should_dispatch_message(message, bot_user_id=999) is True


def test_dispatches_when_directly_mentioning_the_bot_user() -> None:
    message = _message(content="<@999> can you help with roadmap planning?")

    assert should_dispatch_message(message, bot_user_id=999) is True


def test_ignores_unaddressed_messages() -> None:
    message = _message(content="We should probably revisit onboarding metrics.")

    assert should_dispatch_message(message, bot_user_id=999) is False
