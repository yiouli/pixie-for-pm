from __future__ import annotations


def detect_direct_bot_mention(content: str, *, bot_user_id: int | None) -> bool:
    if bot_user_id is None:
        return False

    direct_mentions = (f"<@{bot_user_id}>", f"<@!{bot_user_id}>")
    normalized_content = content.casefold()
    return any(token.casefold() in normalized_content for token in direct_mentions)


def detect_reply_to_bot(*, reply_author_id: int | None, bot_user_id: int | None) -> bool:
    return (
        reply_author_id is not None
        and bot_user_id is not None
        and reply_author_id == bot_user_id
    )
