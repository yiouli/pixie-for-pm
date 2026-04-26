from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import Protocol

import discord
from discord import app_commands

from pixie_for_pm.agents.registry import build_product_manager_handler
from pixie_for_pm.config.settings import AppSettings, load_settings
from pixie_for_pm.discord.commands.settings import install_settings_command
from pixie_for_pm.discord.normalization import (
    detect_direct_bot_mention,
    detect_reply_to_bot,
)
from pixie_for_pm.discord.routing import build_dispatch_request
from pixie_for_pm.domain.models import AgentMessage, AgentRole, IncomingDiscordMessage
from pixie_for_pm.integrations.toolset import build_toolset_initializer
from pixie_for_pm.orchestration.runtime import PixieOrchestrator


def should_dispatch_message(
    message: IncomingDiscordMessage,
    *,
    bot_user_id: int | None,
) -> bool:
    return message.directly_mentions_bot or message.is_reply_to_bot


def compose_public_reply(transcript: Sequence[AgentMessage]) -> str:
    messages = [
        message.content.strip() for message in transcript if message.content.strip()
    ]
    if not messages:
        raise RuntimeError("Orchestrator returned no user-visible messages.")
    return "\n\n".join(messages)


class DiscordRuntime(Protocol):
    async def start(self) -> None: ...

    async def stop(self) -> None: ...


class PixieDiscordBot(discord.Client):
    def __init__(self, settings: AppSettings) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents)
        self._settings = settings
        self._orchestrator = PixieOrchestrator(
            settings.langgraph_checkpoint_path,
            agent_handlers={
                AgentRole.PRODUCT_MANAGER: build_product_manager_handler(
                    model=settings.product_manager_model,
                    openai_api_key=settings.openai_api_key,
                )
            },
            toolset_initializer=build_toolset_initializer(settings),
        )
        self.tree = app_commands.CommandTree(self)
        install_settings_command(self.tree, settings)
        self._ready_guild_sync_complete = False

    async def setup_hook(self) -> None:
        await self._orchestrator.__aenter__()

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
        await self._publish_transcript(
            self._response_channel(message), result.transcript
        )

    def _normalize_message(
        self,
        message: discord.Message,
        *,
        bot_user_id: int | None,
    ) -> IncomingDiscordMessage:
        guild = message.guild
        if guild is None:
            raise RuntimeError("Guild context is required for Discord dispatch.")

        thread = self._message_thread(message)
        return IncomingDiscordMessage(
            discord_message_id=message.id,
            discord_server_id=str(guild.id),
            channel_id=message.channel.id,
            thread_id=str(thread.id) if thread is not None else None,
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
        referenced_message = self._resolved_reply_message(message)
        if referenced_message is None:
            return None

        return referenced_message.author.id

    def _resolved_reply_message(
        self,
        message: discord.Message,
    ) -> discord.Message | None:
        reference = message.reference
        if reference is None or not isinstance(reference.resolved, discord.Message):
            return None
        return reference.resolved

    def _message_thread(self, message: discord.Message) -> discord.Thread | None:
        if isinstance(message.channel, discord.Thread):
            return message.channel

        referenced_message = self._resolved_reply_message(message)
        if referenced_message is None:
            return None

        thread = getattr(referenced_message, "thread", None)
        if isinstance(thread, discord.Thread):
            return thread
        return None

    def _is_reply_to_bot_message(self, message: discord.Message) -> bool:
        bot_user_id = self.user.id if self.user is not None else None
        return detect_reply_to_bot(
            reply_author_id=self._reply_author_id(message),
            bot_user_id=bot_user_id,
        )

    def _response_channel(self, message: discord.Message) -> object:
        thread = self._message_thread(message)
        if thread is not None:
            return thread
        if self._is_reply_to_bot_message(message):
            return message
        return message.channel

    async def _publish_transcript(
        self,
        channel: object,
        transcript: Sequence[AgentMessage],
    ) -> None:
        reply_send = getattr(channel, "reply", None)
        if reply_send is not None:
            await reply_send(compose_public_reply(transcript), mention_author=False)
            return

        channel_send = getattr(channel, "send", None)
        if channel_send is None:
            raise RuntimeError(
                "Configured Discord channel does not support sending messages."
            )
        await channel_send(compose_public_reply(transcript))


class ManagedDiscordRuntime:
    def __init__(self, settings: AppSettings) -> None:
        self._bot = PixieDiscordBot(settings)
        self._discord_bot_token = settings.discord_bot_token
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._task is not None:
            return

        self._task = asyncio.create_task(self._bot.start(self._discord_bot_token))
        ready_task = asyncio.create_task(self._bot.wait_until_ready())
        done, _ = await asyncio.wait(
            {self._task, ready_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        if self._task in done:
            ready_task.cancel()
            await self._task
        await ready_task

    async def stop(self) -> None:
        task = self._task
        if task is None:
            return

        self._task = None
        if not self._bot.is_closed():
            await self._bot.close()
        await task


def main() -> None:
    settings = load_settings()
    bot = PixieDiscordBot(settings)
    bot.run(settings.discord_bot_token)
