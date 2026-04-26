from __future__ import annotations

from collections.abc import Sequence

import discord
from discord import app_commands

from pixie_for_pm.config.settings import AppSettings, load_settings
from pixie_for_pm.discord.commands.settings import install_settings_command
from pixie_for_pm.discord.normalization import (
    detect_direct_bot_mention,
    detect_reply_to_bot,
)
from pixie_for_pm.discord.routing import build_dispatch_request
from pixie_for_pm.domain.models import AgentMessage, IncomingDiscordMessage
from pixie_for_pm.orchestration.runtime import PixieOrchestrator


def should_dispatch_message(
    message: IncomingDiscordMessage,
    *,
    bot_user_id: int | None,
) -> bool:
    return message.directly_mentions_bot or message.is_reply_to_bot


def compose_public_reply(transcript: Sequence[AgentMessage]) -> str:
    messages = [message.content.strip() for message in transcript if message.content.strip()]
    if not messages:
        raise RuntimeError("Orchestrator returned no user-visible messages.")
    return "\n\n".join(messages)


class PixieDiscordBot(discord.Client):
    def __init__(self, settings: AppSettings) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents)
        self._settings = settings
        self._orchestrator = PixieOrchestrator(settings.langgraph_checkpoint_path)
        self.tree = app_commands.CommandTree(self)
        install_settings_command(self.tree, settings)
        self._ready_guild_sync_complete = False

    async def setup_hook(self) -> None:
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
        await super().close()

    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or message.webhook_id is not None:
            return

        if message.guild is None:
            return

        bot_user_id = self.user.id if self.user is not None else None
        incoming_message = self._normalize_message(message, bot_user_id=bot_user_id)
        if not should_dispatch_message(
            incoming_message,
            bot_user_id=bot_user_id,
        ):
            return

        dispatch_request = build_dispatch_request(incoming_message)
        result = await self._orchestrator.dispatch(dispatch_request)
        await self._publish_transcript(message.channel, result.transcript)

    def _normalize_message(
        self,
        message: discord.Message,
        *,
        bot_user_id: int | None,
    ) -> IncomingDiscordMessage:
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
            directly_mentions_bot=detect_direct_bot_mention(
                message.content,
                bot_user_id=bot_user_id,
            ),
            is_reply_to_bot=detect_reply_to_bot(
                reply_author_id=self._reply_author_id(message),
                bot_user_id=bot_user_id,
            ),
        )

    def _reply_author_id(self, message: discord.Message) -> int | None:
        reference = message.reference
        if reference is None or not isinstance(reference.resolved, discord.Message):
            return None

        return reference.resolved.author.id

    async def _publish_transcript(
        self,
        channel: object,
        transcript: Sequence[AgentMessage],
    ) -> None:
        channel_send = getattr(channel, "send", None)
        if channel_send is None:
            raise RuntimeError(
                "Configured Discord channel does not support sending messages."
            )
        await channel_send(compose_public_reply(transcript))


def main() -> None:
    settings = load_settings()
    bot = PixieDiscordBot(settings)
    bot.run(settings.discord_bot_token)
