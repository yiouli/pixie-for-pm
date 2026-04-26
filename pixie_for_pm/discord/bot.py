from __future__ import annotations

import aiohttp
import discord
from discord import app_commands

from pixie_for_pm.config.settings import AppSettings, load_settings
from pixie_for_pm.discord.commands.settings import install_settings_command
from pixie_for_pm.discord.normalization import (
    detect_mentioned_agents,
    detect_reply_agent,
)
from pixie_for_pm.discord.routing import build_dispatch_request
from pixie_for_pm.domain.models import AgentMessage, IncomingDiscordMessage
from pixie_for_pm.orchestration.runtime import PixieOrchestrator


class PixieDiscordBot(discord.Client):
    def __init__(self, settings: AppSettings) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents)
        self._settings = settings
        self._orchestrator = PixieOrchestrator(settings.langgraph_checkpoint_path)
        self._webhook_session: aiohttp.ClientSession | None = None
        self.tree = app_commands.CommandTree(self)
        install_settings_command(self.tree, settings)

    async def setup_hook(self) -> None:
        self._webhook_session = aiohttp.ClientSession()
        await self._orchestrator.__aenter__()
        await self.tree.sync(guild=discord.Object(id=self._settings.discord_guild_id))

    async def close(self) -> None:
        await self._orchestrator.__aexit__(None, None, None)
        if self._webhook_session is not None:
            await self._webhook_session.close()
        await super().close()

    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or message.webhook_id is not None:
            return

        if message.guild is None or message.guild.id != self._settings.discord_guild_id:
            return

        if not self._is_supported_channel(message.channel):
            return

        incoming_message = self._normalize_message(message)
        dispatch_request = build_dispatch_request(incoming_message)
        result = await self._orchestrator.dispatch(dispatch_request)
        for agent_message in result.transcript:
            await self._publish_agent_message(message.channel, agent_message)

    def _normalize_message(self, message: discord.Message) -> IncomingDiscordMessage:
        reply_display_name = self._reply_display_name(message)
        return IncomingDiscordMessage(
            discord_message_id=message.id,
            channel_id=message.channel.id,
            thread_id=(
                str(message.channel.id)
                if isinstance(message.channel, discord.Thread)
                else None
            ),
            author_id=message.author.id,
            content=message.content,
            mentioned_agents=detect_mentioned_agents(
                message.content, self._settings.personas
            ),
            reply_to_agent=detect_reply_agent(
                reply_display_name, self._settings.personas
            ),
        )

    def _reply_display_name(self, message: discord.Message) -> str | None:
        reference = message.reference
        if reference is None or not isinstance(reference.resolved, discord.Message):
            return None

        author = reference.resolved.author
        return getattr(author, "display_name", author.name)

    def _is_supported_channel(self, channel: object) -> bool:
        if isinstance(channel, discord.Thread):
            thread = channel
            return thread.parent_id == self._settings.discord_orchestration_channel_id
        return (
            getattr(channel, "id", None)
            == self._settings.discord_orchestration_channel_id
        )

    async def _publish_agent_message(
        self,
        channel: object,
        agent_message: AgentMessage,
    ) -> None:
        persona = self._settings.personas[agent_message.agent]
        if self._webhook_session is not None and persona.webhook_url is not None:
            webhook = discord.Webhook.from_url(
                persona.webhook_url, session=self._webhook_session
            )
            await webhook.send(
                agent_message.content,
                username=persona.display_name,
                thread=(
                    channel
                    if isinstance(channel, discord.Thread)
                    else discord.utils.MISSING
                ),
            )
            return

        channel_send = getattr(channel, "send", None)
        if channel_send is None:
            raise RuntimeError(
                "Configured Discord channel does not support sending messages."
            )
        await channel_send(f"**{persona.display_name}:** {agent_message.content}")


def main() -> None:
    settings = load_settings()
    bot = PixieDiscordBot(settings)
    bot.run(settings.discord_bot_token)
