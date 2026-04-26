from typing import cast

import discord
import pytest

from pixie_for_pm.config.settings import load_settings
from pixie_for_pm.discord.commands.settings import (
    build_settings_url,
    respond_with_settings_link,
)


def test_build_settings_url_includes_guild_id_query_parameter() -> None:
    settings = load_settings(
        {
            "DISCORD_BOT_TOKEN": "discord-token",
            "WEB_APP_URL": "https://app.pixie.test",
        }
    )

    assert build_settings_url(settings, guild_id=987654321) == (
        "https://app.pixie.test/settings?server_id=987654321"
    )


def test_build_settings_url_requires_web_app_configuration() -> None:
    settings = load_settings(
        {
            "DISCORD_BOT_TOKEN": "discord-token",
        }
    )

    with pytest.raises(RuntimeError, match="WEB_APP_URL"):
        build_settings_url(settings, guild_id=987654321)


class _FakeResponse:
    def __init__(self) -> None:
        self.deferred = False
        self.ephemeral: bool | None = None

    async def defer(self, *, ephemeral: bool = False) -> None:
        self.deferred = True
        self.ephemeral = ephemeral


class _FakeGuild:
    def __init__(self, guild_id: int) -> None:
        self.id = guild_id


class _FakeInteraction:
    def __init__(self, guild_id: int | None) -> None:
        self.guild = None if guild_id is None else _FakeGuild(guild_id)
        self.response = _FakeResponse()
        self.edits: list[dict[str, object]] = []

    async def edit_original_response(self, **kwargs: object) -> None:
        self.edits.append(kwargs)


@pytest.mark.asyncio
async def test_settings_command_uses_deferred_ephemeral_reply() -> None:
    settings = load_settings(
        {
            "DISCORD_BOT_TOKEN": "discord-token",
            "WEB_APP_URL": "https://app.pixie.test",
        }
    )
    interaction = _FakeInteraction(guild_id=987654321)

    await respond_with_settings_link(
        cast(discord.Interaction[discord.Client], interaction),
        settings,
    )

    assert interaction.response.deferred is True
    assert interaction.response.ephemeral is True
    assert interaction.edits[0]["content"] == "Configure your integrations:"
    assert interaction.edits[0]["view"] is not None


@pytest.mark.asyncio
async def test_settings_command_reports_dm_usage_via_deferred_reply() -> None:
    settings = load_settings(
        {
            "DISCORD_BOT_TOKEN": "discord-token",
            "WEB_APP_URL": "https://app.pixie.test",
        }
    )
    interaction = _FakeInteraction(guild_id=None)

    await respond_with_settings_link(
        cast(discord.Interaction[discord.Client], interaction),
        settings,
    )

    assert interaction.response.deferred is True
    assert interaction.edits == [
        {"content": "This command can only be used in a server.", "view": None}
    ]
