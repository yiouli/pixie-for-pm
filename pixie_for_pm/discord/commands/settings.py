from __future__ import annotations

import discord
from discord import app_commands

from pixie_for_pm.config.settings import AppSettings


def build_settings_url(settings: AppSettings, *, guild_id: int) -> str:
    if settings.web_app_url is None:
        raise RuntimeError("WEB_APP_URL must be configured to use /settings.")
    base_url = settings.web_app_url.rstrip("/")
    return f"{base_url}/settings?server_id={guild_id}"


async def respond_with_settings_link(
    interaction: discord.Interaction[discord.Client],
    settings: AppSettings,
) -> None:
    await interaction.response.defer(ephemeral=True)

    if interaction.guild is None:
        await interaction.edit_original_response(
            content="This command can only be used in a server.",
            view=None,
        )
        return

    try:
        url = build_settings_url(settings, guild_id=interaction.guild.id)
    except RuntimeError as exc:
        await interaction.edit_original_response(content=str(exc), view=None)
        return

    view = discord.ui.View()
    view.add_item(
        discord.ui.Button(
            label="Open Settings",
            url=url,
            style=discord.ButtonStyle.link,
        )
    )
    await interaction.edit_original_response(
        content="Configure your integrations:",
        view=view,
    )


def install_settings_command(
    tree: app_commands.CommandTree[discord.Client],
    settings: AppSettings,
) -> None:
    @tree.command(
        name="settings",
        description="Configure integrations for the PM agents",
    )
    async def settings_command(
        interaction: discord.Interaction[discord.Client],
    ) -> None:
        await respond_with_settings_link(interaction, settings)
