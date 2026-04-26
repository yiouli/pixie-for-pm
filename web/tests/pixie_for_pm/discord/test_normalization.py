from pixie_for_pm.discord.normalization import (
    detect_direct_bot_mention,
    detect_reply_to_bot,
)


def test_detect_direct_bot_mention_matches_both_discord_formats() -> None:
    mentioned = detect_direct_bot_mention(
        "<@123> can you help? <@!123> also works.",
        bot_user_id=123,
    )

    assert mentioned is True


def test_detect_reply_to_bot_matches_the_bot_author_id() -> None:
    assert detect_reply_to_bot(reply_author_id=123, bot_user_id=123) is True


def test_detect_reply_to_bot_rejects_other_authors() -> None:
    assert detect_reply_to_bot(reply_author_id=456, bot_user_id=123) is False
