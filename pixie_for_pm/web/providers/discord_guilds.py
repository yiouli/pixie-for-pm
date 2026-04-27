"""Discord guild metadata lookup for the settings web app."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import httpx

_DISCORD_GUILD_URL = "https://discord.com/api/v10/guilds/{guild_id}"
_DISCORD_GUILD_ICON_URL = (
    "https://cdn.discordapp.com/icons/{guild_id}/{icon}.{ext}?size=128"
)


@dataclass(frozen=True)
class DiscordGuild:
    id: str
    name: str
    icon_url: str | None


class DiscordGuildLookupError(Exception):
    """Raised when Discord guild metadata cannot be fetched."""


class DiscordGuildService(Protocol):
    async def get_guild(self, discord_server_id: str) -> DiscordGuild | None:
        """Return guild metadata for *discord_server_id*, or ``None``."""
        ...


class StaticDiscordGuildService:
    def __init__(self, guilds: dict[str, DiscordGuild] | None = None) -> None:
        self._guilds = guilds or {}

    async def get_guild(self, discord_server_id: str) -> DiscordGuild | None:
        return self._guilds.get(discord_server_id)


class HttpDiscordGuildService:
    def __init__(
        self,
        bot_token: str,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._bot_token = bot_token
        self._transport = transport

    async def get_guild(self, discord_server_id: str) -> DiscordGuild | None:
        async with httpx.AsyncClient(transport=self._transport, timeout=15.0) as client:
            response = await client.get(
                _DISCORD_GUILD_URL.format(guild_id=discord_server_id),
                headers={"Authorization": f"Bot {self._bot_token}"},
            )

        if response.status_code == 404:
            return None
        if response.status_code != 200:
            raise DiscordGuildLookupError(
                f"Discord guild fetch failed: {response.status_code}"
            )

        payload = response.json()
        return DiscordGuild(
            id=str(payload["id"]),
            name=str(payload["name"]),
            icon_url=_build_icon_url(
                guild_id=str(payload["id"]),
                icon_hash=_optional_text(payload.get("icon")),
            ),
        )


def _build_icon_url(*, guild_id: str, icon_hash: str | None) -> str | None:
    if icon_hash is None:
        return None
    extension = "gif" if icon_hash.startswith("a_") else "png"
    return _DISCORD_GUILD_ICON_URL.format(
        guild_id=guild_id,
        icon=icon_hash,
        ext=extension,
    )


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    return str(value)
