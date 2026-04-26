from pixie_for_pm.discord.bot import should_dispatch_message
from pixie_for_pm.domain.models import IncomingDiscordMessage


def _message(
    *,
    content: str,
    directly_mentions_bot: bool = False,
    is_reply_to_bot: bool = False,
) -> IncomingDiscordMessage:
    return IncomingDiscordMessage(
        discord_message_id=1,
        channel_id=2,
        thread_id=None,
        author_id=3,
        content=content,
        directly_mentions_bot=directly_mentions_bot,
        is_reply_to_bot=is_reply_to_bot,
    )


def test_dispatches_when_replying_to_bot_message() -> None:
    message = _message(content="Can you continue that analysis?", is_reply_to_bot=True)

    assert should_dispatch_message(message, bot_user_id=999) is True


def test_dispatches_when_directly_mentioning_the_bot_user() -> None:
    message = _message(
        content="<@999> can you help with roadmap planning?",
        directly_mentions_bot=True,
    )

    assert should_dispatch_message(message, bot_user_id=999) is True


def test_ignores_messages_that_only_look_like_mentions_when_not_normalized() -> None:
    message = _message(content="<@999> can you help with roadmap planning?")

    assert should_dispatch_message(message, bot_user_id=999) is False


def test_ignores_unaddressed_messages() -> None:
    message = _message(content="We should probably revisit onboarding metrics.")

    assert should_dispatch_message(message, bot_user_id=999) is False
