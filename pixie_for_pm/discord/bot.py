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


def should_dispatch_message(
    message: IncomingDiscordMessage,
    *,
    bot_user_id: int | None,
) -> bool:
    if message.mentioned_agents:
        return True
    if message.reply_to_agent is not None:
        return True
    if bot_user_id is None:
        return False
    direct_mentions = (f"<@{bot_user_id}>", f"<@!{bot_user_id}>")
    return any(token in message.content for token in direct_mentions)


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
        self._ready_guild_sync_complete = False

    async def setup_hook(self) -> None:
        self._webhook_session = aiohttp.ClientSession()
        await self._orchestrator.__aenter__()
        await self.tree.sync()

    async def on_ready(self) -> None:
        if self._ready_guild_sync_complete:
            return
        self._ready_guild_sync_complete = True
        for guild in self.guilds:
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)

    async def on_guild_join(self, guild: discord.Guild) -> None:
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)

    async def close(self) -> None:
        await self._orchestrator.__aexit__(None, None, None)
        if self._webhook_session is not None:
            await self._webhook_session.close()
        await super().close()

    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or message.webhook_id is not None:
            return

        if message.guild is None:
            return

        incoming_message = self._normalize_message(message)
        if not should_dispatch_message(
            incoming_message,
            bot_user_id=self.user.id if self.user is not None else None,
        ):
            return

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
