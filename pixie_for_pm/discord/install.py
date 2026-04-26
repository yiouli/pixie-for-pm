from __future__ import annotations

from urllib.parse import urlencode

import discord

_DISCORD_BOT_AUTHORIZE_URL = "https://discord.com/oauth2/authorize"


def default_install_permissions() -> int:
    permissions = discord.Permissions.none()
    permissions.view_channel = True
    permissions.send_messages = True
    permissions.read_message_history = True
    permissions.create_public_threads = True
    permissions.send_messages_in_threads = True
    return permissions.value


def build_bot_install_url(
    application_id: str,
    *,
    permissions: int,
    guild_id: int | None = None,
) -> str:
    query: list[tuple[str, str]] = [
        ("client_id", application_id),
        ("scope", "bot applications.commands"),
        ("permissions", str(permissions)),
    ]
    if guild_id is not None:
        query.extend(
            [
                ("guild_id", str(guild_id)),
                ("disable_guild_select", "true"),
            ]
        )
    return f"{_DISCORD_BOT_AUTHORIZE_URL}?{urlencode(query)}"
