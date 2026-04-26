from pixie_for_pm.discord.routing import build_dispatch_request
from pixie_for_pm.domain.models import AgentRole, IncomingDiscordMessage


def test_routes_explicit_agent_mentions_first() -> None:
    request = build_dispatch_request(
        IncomingDiscordMessage(
            discord_message_id=101,
            channel_id=202,
            thread_id=None,
            author_id=303,
            content="@market-analyst can you size this category?",
            mentioned_agents=(AgentRole.MARKET_ANALYST,),
            reply_to_agent=AgentRole.USER_RESEARCHER,
        )
    )

    assert request.target_agent is AgentRole.MARKET_ANALYST
    assert request.reason == "mentioned_agent"


def test_routes_replys_to_the_agent_that_started_the_thread() -> None:
    request = build_dispatch_request(
        IncomingDiscordMessage(
            discord_message_id=111,
            channel_id=222,
            thread_id="thread-1",
            author_id=333,
            content="Can you expand on that?",
            mentioned_agents=(),
            reply_to_agent=AgentRole.PRODUCT_DESIGNER,
        )
    )

    assert request.target_agent is AgentRole.PRODUCT_DESIGNER
    assert request.reason == "reply_to_agent"


def test_defaults_new_unaddressed_messages_to_product_manager() -> None:
    request = build_dispatch_request(
        IncomingDiscordMessage(
            discord_message_id=121,
            channel_id=232,
            thread_id=None,
            author_id=343,
            content="We should explore an AI PM copilot.",
            mentioned_agents=(),
            reply_to_agent=None,
        )
    )

    assert request.target_agent is AgentRole.PRODUCT_MANAGER
    assert request.reason == "default_product_manager"
