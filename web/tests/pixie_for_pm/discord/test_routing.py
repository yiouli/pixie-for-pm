from pixie_for_pm.discord.routing import build_dispatch_request
from pixie_for_pm.domain.models import AgentRole, IncomingDiscordMessage


def test_routes_direct_bot_mentions_to_the_product_manager_entrypoint() -> None:
    request = build_dispatch_request(
        IncomingDiscordMessage(
            discord_message_id=101,
            discord_server_id="discord-server-101",
            channel_id=202,
            thread_id=None,
            author_id=303,
            content="<@999> can you size this category?",
            directly_mentions_bot=True,
            is_reply_to_bot=False,
        )
    )

    assert request.target_agent is AgentRole.DISPATCHER
    assert request.reason == "direct_bot_mention"


def test_routes_bot_replies_back_to_the_product_manager_entrypoint() -> None:
    request = build_dispatch_request(
        IncomingDiscordMessage(
            discord_message_id=111,
            discord_server_id="discord-server-111",
            channel_id=222,
            thread_id="thread-1",
            author_id=333,
            content="Can you expand on that?",
            directly_mentions_bot=False,
            is_reply_to_bot=True,
        )
    )

    assert request.target_agent is AgentRole.DISPATCHER
    assert request.reason == "reply_to_bot"


def test_routes_other_messages_to_the_product_manager_entrypoint() -> None:
    request = build_dispatch_request(
        IncomingDiscordMessage(
            discord_message_id=121,
            discord_server_id="discord-server-121",
            channel_id=232,
            thread_id=None,
            author_id=343,
            content="We should explore an AI PM copilot.",
            directly_mentions_bot=False,
            is_reply_to_bot=False,
        )
    )

    assert request.target_agent is AgentRole.DISPATCHER
    assert request.reason == "discord_message"
