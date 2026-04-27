from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Awaitable, Callable, Sequence
from contextlib import suppress
from dataclasses import replace
from typing import Any, Protocol, cast

import discord
from discord import app_commands

from pixie_for_pm.agents.registry import (
    build_product_designer_handler,
    build_product_manager_handler,
    build_user_researcher_handler,
)
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

logger = logging.getLogger(__name__)

DISCORD_MESSAGE_LIMIT = 2000
DISCORD_STREAM_UPDATE_INTERVAL = 500
DISCORD_ERROR_TITLE = "Pixie couldn't complete that request"
DISCORD_STATUS_TITLE = "Pixie is working"
DEFAULT_THREAD_NAME = "pixie chat"
MAX_THREAD_NAME_LENGTH = 60
_DISCORD_MENTION_PATTERN = re.compile(r"<@!?\d+>")
_MARKDOWN_TABLE_SEPARATOR_PATTERN = re.compile(r"^:?-{3,}:?$")
_LEADING_REQUEST_PATTERN = re.compile(
    r"^(?:please\s+)?(?:(?:can|could|would|will)\s+you\s+)",
    re.IGNORECASE,
)


def should_dispatch_message(
    message: IncomingDiscordMessage,
    *,
    bot_user_id: int | None,
    has_thread_context: bool = False,
) -> bool:
    del bot_user_id
    return (
        message.directly_mentions_bot or message.is_reply_to_bot or has_thread_context
    )


def compose_public_reply(transcript: Sequence[AgentMessage]) -> str:
    messages = [
        message.content.strip() for message in transcript if message.content.strip()
    ]
    if not messages:
        raise RuntimeError("Orchestrator returned no user-visible messages.")
    return "\n\n".join(messages)


def split_discord_response(
    content: str,
    *,
    limit: int | None = None,
    trim_whitespace: bool = True,
) -> list[str]:
    normalized_content = content.strip() if trim_whitespace else content
    if normalized_content == "":
        return []

    active_limit = DISCORD_MESSAGE_LIMIT if limit is None else limit

    chunks: list[str] = []
    remaining = normalized_content
    while len(remaining) > active_limit:
        split_at = _natural_break_index(remaining, active_limit)
        if split_at <= 0:
            split_at = active_limit

        chunk = remaining[:split_at].rstrip()
        if chunk == "":
            chunk = remaining[:active_limit].rstrip()
            split_at = len(chunk)

        chunks.append(chunk)
        remaining = remaining[split_at:].lstrip()

    chunks.append(remaining)
    return chunks


def _natural_break_index(content: str, limit: int) -> int:
    candidate = content[:limit]
    for delimiter in ("\n\n", "\n"):
        index = candidate.rfind(delimiter)
        if index > 0:
            return index

    for delimiter in (". ", "? ", "! ", ".\n", "?\n", "!\n"):
        index = candidate.rfind(delimiter)
        if index > 0:
            return index + 1

    return limit


def _stream_chunk_limit() -> int:
    return min(DISCORD_STREAM_UPDATE_INTERVAL, DISCORD_MESSAGE_LIMIT)


def _parse_markdown_table_row(line: str) -> list[str]:
    stripped = line.strip()
    if not stripped.startswith("|") or not stripped.endswith("|"):
        return []
    return [cell.strip() for cell in stripped[1:-1].split("|")]


def _is_markdown_table_separator(line: str, *, expected_columns: int) -> bool:
    cells = _parse_markdown_table_row(line)
    if len(cells) != expected_columns or expected_columns == 0:
        return False
    return all(_MARKDOWN_TABLE_SEPARATOR_PATTERN.fullmatch(cell) for cell in cells)


def _render_markdown_table(lines: Sequence[str]) -> list[str]:
    header_cells = _parse_markdown_table_row(lines[0])
    data_cells = [_parse_markdown_table_row(line) for line in lines[2:]]
    widths = [len(cell) for cell in header_cells]
    for row in data_cells:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], len(cell))

    rendered_rows = [
        " | ".join(
            cell.ljust(widths[index]) for index, cell in enumerate(header_cells)
        ).rstrip(),
        "+".join("-" * width for width in widths),
    ]
    for row in data_cells:
        rendered_rows.append(
            " | ".join(
                cell.ljust(widths[index]) for index, cell in enumerate(row)
            ).rstrip()
        )
    return ["```text", *rendered_rows, "```"]


def _render_discord_content(content: str) -> str:
    lines = content.split("\n")
    rendered_lines: list[str] = []
    index = 0
    while index < len(lines):
        header_cells = _parse_markdown_table_row(lines[index])
        if (
            header_cells
            and index + 1 < len(lines)
            and _is_markdown_table_separator(
                lines[index + 1], expected_columns=len(header_cells)
            )
        ):
            table_lines = [lines[index], lines[index + 1]]
            index += 2
            while index < len(lines):
                row_cells = _parse_markdown_table_row(lines[index])
                if len(row_cells) != len(header_cells):
                    break
                table_lines.append(lines[index])
                index += 1
            rendered_lines.extend(_render_markdown_table(table_lines))
            continue

        rendered_lines.append(lines[index])
        index += 1

    return "\n".join(rendered_lines)


def _error_embed(description: str) -> discord.Embed:
    return discord.Embed(
        title=DISCORD_ERROR_TITLE,
        description=description,
        colour=discord.Colour.red(),
    )


def _status_embed(description: str) -> discord.Embed:
    return discord.Embed(
        title=DISCORD_STATUS_TITLE,
        description=description,
        colour=discord.Colour.orange(),
    )


def build_thread_title(content: str) -> str:
    normalized = _DISCORD_MENTION_PATTERN.sub(" ", content)
    normalized = re.sub(r"\s+", " ", normalized).strip(" \t\n\r:,-")
    normalized = _LEADING_REQUEST_PATTERN.sub("", normalized)
    normalized = normalized.strip(" \t\n\r?!.,:;-")
    if normalized == "":
        return DEFAULT_THREAD_NAME

    if len(normalized) <= MAX_THREAD_NAME_LENGTH:
        return normalized

    truncated = normalized[: MAX_THREAD_NAME_LENGTH - 1].rstrip()
    last_space = truncated.rfind(" ")
    if last_space >= 24:
        truncated = truncated[:last_space].rstrip()
    return f"{truncated}…"


class DiscordRuntime(Protocol):
    async def start(self) -> None: ...

    async def stop(self) -> None: ...


class _DiscordProgressReporter:
    def __init__(
        self,
        *,
        source_message: discord.Message,
        response_channel: object,
    ) -> None:
        self._source_message = source_message
        self._response_channel = response_channel
        self._status_message: object | None = None
        self._typing_task: asyncio.Task[None] | None = None
        self._last_status: str | None = None
        self._stream_buffer: str = ""
        self._has_stream_activity = False

    async def start(self) -> None:
        await self._add_eyes_reaction()
        self._typing_task = asyncio.create_task(self._typing_loop())
        await self.emit("Thinking...")

    async def emit(self, status: str) -> None:
        normalized_status = status.strip()
        if normalized_status == "" or normalized_status == self._last_status:
            return

        self._last_status = normalized_status
        await self._trigger_typing_once()
        if self._has_stream_activity or self._stream_buffer != "":
            return

        status_embed = _status_embed(normalized_status)
        if self._status_message is None:
            self._status_message = await self._send_response(
                "",
                embed=status_embed,
                keep_typing=True,
            )
            return

        await self._edit_status_message("", embed=status_embed, keep_typing=True)

    async def stream_content(self, delta: str) -> None:
        if delta == "":
            return

        self._has_stream_activity = True
        self._stream_buffer += delta
        await self._flush_stream_buffer(final=False)

    async def publish_transcript(self, transcript: Sequence[AgentMessage]) -> None:
        final_content = compose_public_reply(transcript)
        if final_content == "":
            raise RuntimeError("Orchestrator returned no user-visible messages.")

        if not self._has_stream_activity:
            self._stream_buffer = final_content
        await self._flush_stream_buffer(final=True)
        await self._delete_status_message()
        self._last_status = final_content

    async def publish_error(self, content: str) -> None:
        embed = _error_embed(content)
        if self._status_message is None:
            self._status_message = await self._send_response(
                "",
                embed=embed,
                keep_typing=False,
            )
            self._last_status = content
            return

        await self._edit_status_message("", embed=embed, keep_typing=False)
        self._last_status = content

    async def close(self) -> None:
        if self._typing_task is None:
            return

        self._typing_task.cancel()
        with suppress(asyncio.CancelledError):
            await self._typing_task

    async def _add_eyes_reaction(self) -> None:
        with suppress(discord.HTTPException):
            await self._source_message.add_reaction("\N{EYES}")

    async def _typing_loop(self) -> None:
        try:
            while True:
                await self._trigger_typing_once()
                await asyncio.sleep(8)
        except asyncio.CancelledError:
            return

    async def _trigger_typing_once(self) -> None:
        target = self._typing_target()
        trigger_typing = cast(
            Callable[[], Awaitable[None]] | None,
            getattr(target, "trigger_typing", None),
        )
        if trigger_typing is not None:
            with suppress(discord.HTTPException):
                await trigger_typing()
            return

        typing_factory = cast(
            Callable[[], object] | None, getattr(target, "typing", None)
        )
        if typing_factory is None:
            return

        with suppress(discord.HTTPException):
            async with cast(Any, typing_factory()):
                return

    def _typing_target(self) -> object:
        if hasattr(self._response_channel, "trigger_typing") or hasattr(
            self._response_channel, "typing"
        ):
            return self._response_channel
        return self._source_message.channel

    async def _send_response(
        self,
        content: str,
        *,
        embed: discord.Embed | None = None,
        keep_typing: bool = False,
    ) -> object:
        reply_send = cast(
            Callable[..., Awaitable[object]] | None,
            getattr(self._response_channel, "reply", None),
        )
        if reply_send is not None:
            message = await reply_send(content, mention_author=False, embed=embed)
            if keep_typing:
                await self._trigger_typing_once()
            return message

        channel_send = cast(
            Callable[..., Awaitable[object]] | None,
            getattr(self._response_channel, "send", None),
        )
        if channel_send is None:
            raise RuntimeError(
                "Configured Discord channel does not support sending messages."
            )
        message = await channel_send(content, embed=embed)
        if keep_typing:
            await self._trigger_typing_once()
        return message

    async def _send_follow_up(self, content: str, *, keep_typing: bool) -> object:
        rendered_content = _render_discord_content(content)
        channel_send = cast(
            Callable[..., Awaitable[object]] | None,
            getattr(self._response_channel, "send", None),
        )
        if channel_send is not None:
            message = await channel_send(rendered_content)
            if keep_typing:
                await self._trigger_typing_once()
            return message
        return await self._send_response(rendered_content, keep_typing=keep_typing)

    async def _edit_status_message(
        self,
        content: str,
        *,
        embed: discord.Embed | None = None,
        keep_typing: bool = False,
    ) -> None:
        if self._status_message is None:
            self._status_message = await self._send_response(
                content,
                embed=embed,
                keep_typing=keep_typing,
            )
            return

        if await self._edit_message(
            self._status_message,
            content,
            embed=embed,
            keep_typing=keep_typing,
        ):
            return

        self._status_message = await self._send_response(
            content,
            embed=embed,
            keep_typing=keep_typing,
        )

    async def _edit_message(
        self,
        message: object | None,
        content: str,
        *,
        embed: discord.Embed | None = None,
        keep_typing: bool = False,
    ) -> bool:
        if message is None:
            return False

        edit_message = cast(
            Callable[..., Awaitable[object]] | None,
            getattr(message, "edit", None),
        )
        if edit_message is None:
            return False

        await edit_message(content=content, embed=embed)
        if keep_typing:
            await self._trigger_typing_once()
        return True

    async def _delete_status_message(self) -> None:
        if self._status_message is None:
            return

        delete_message = cast(
            Callable[[], Awaitable[object]] | None,
            getattr(self._status_message, "delete", None),
        )
        if delete_message is None:
            self._status_message = None
            return

        with suppress(discord.HTTPException):
            await delete_message()
        self._status_message = None

    async def _flush_stream_buffer(self, *, final: bool) -> None:
        while True:
            next_chunk = self._next_stream_chunk(final=final)
            if next_chunk is None:
                return

            split_at, content = next_chunk
            remaining_buffer = self._stream_buffer[split_at:].lstrip()
            await self._send_follow_up(
                content,
                keep_typing=(not final) or remaining_buffer != "",
            )
            self._stream_buffer = remaining_buffer

    def _next_stream_chunk(self, *, final: bool) -> tuple[int, str] | None:
        if self._stream_buffer == "":
            return None

        chunk_limit = _stream_chunk_limit()

        if final and len(self._stream_buffer) <= chunk_limit:
            return (len(self._stream_buffer), self._stream_buffer)

        if len(self._stream_buffer) < chunk_limit:
            return None

        split_at = _natural_break_index(self._stream_buffer, chunk_limit)
        if split_at <= 0:
            split_at = chunk_limit

        content = self._stream_buffer[:split_at].rstrip()
        if content == "":
            content = self._stream_buffer[:chunk_limit].rstrip()
            split_at = len(self._stream_buffer[:chunk_limit])

        return (split_at, content)


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
                ),
                AgentRole.PRODUCT_DESIGNER: build_product_designer_handler(
                    model=settings.product_manager_model,
                    openai_api_key=settings.openai_api_key,
                ),
                AgentRole.USER_RESEARCHER: build_user_researcher_handler(
                    model=settings.product_manager_model,
                    openai_api_key=settings.openai_api_key,
                ),
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
        await self._clear_global_commands()
        for guild in self.guilds:
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)

    async def on_guild_join(self, guild: discord.Guild) -> None:
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)

    async def _clear_global_commands(self) -> None:
        application_id = self.application_id
        if application_id is None:
            app_info = await self.application_info()
            application_id = app_info.id

        try:
            await self.http.bulk_upsert_global_commands(application_id, [])
        except discord.HTTPException:
            logger.warning("Failed to clear stale global Discord application commands.")

    async def close(self) -> None:
        await self._orchestrator.__aexit__(None, None, None)
        await super().close()

    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or message.webhook_id is not None:
            return

        if message.guild is None:
            return

        if self._is_thread_starter_message(message):
            return

        bot_user_id = self.user.id if self.user is not None else None
        incoming_message = self._normalize_message(message, bot_user_id=bot_user_id)
        has_thread_context = await self._thread_has_bot_context(message)
        if not should_dispatch_message(
            incoming_message,
            bot_user_id=bot_user_id,
            has_thread_context=has_thread_context,
        ):
            return

        response_channel = await self._dispatch_response_channel(
            message,
            incoming_message=incoming_message,
        )
        thread_id = getattr(response_channel, "id", None)
        if thread_id is not None and incoming_message.thread_id != str(thread_id):
            incoming_message = replace(incoming_message, thread_id=str(thread_id))

        dispatch_request = build_dispatch_request(incoming_message)
        progress_reporter = _DiscordProgressReporter(
            source_message=message,
            response_channel=response_channel,
        )
        try:
            await progress_reporter.start()
            result = await self._orchestrator.dispatch(
                dispatch_request,
                status_emitter=progress_reporter.emit,
                response_emitter=progress_reporter.stream_content,
            )
            await progress_reporter.publish_transcript(result.transcript)
        except Exception:
            logger.exception(
                "Discord dispatch failed for message %s",
                message.id,
            )
            await progress_reporter.publish_error(
                "Error: Pixie failed to complete this request."
            )
        finally:
            await progress_reporter.close()

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

    async def _thread_has_bot_context(self, message: discord.Message) -> bool:
        if not isinstance(message.channel, discord.Thread):
            return False

        bot_user_id = self.user.id if self.user is not None else None
        if bot_user_id is None:
            return False

        starter_message = getattr(message.channel, "starter_message", None)
        starter_author = getattr(starter_message, "author", None)
        if getattr(starter_author, "id", None) == bot_user_id:
            return True

        try:
            async for thread_message in message.channel.history(limit=25):
                if getattr(thread_message, "id", None) == message.id:
                    continue

                author = getattr(thread_message, "author", None)
                if getattr(author, "id", None) == bot_user_id:
                    return True
        except discord.HTTPException:
            logger.warning(
                "Failed to inspect thread history for Discord message %s",
                message.id,
            )

        return False

    def _is_reply_to_bot_message(self, message: discord.Message) -> bool:
        bot_user_id = self.user.id if self.user is not None else None
        return detect_reply_to_bot(
            reply_author_id=self._reply_author_id(message),
            bot_user_id=bot_user_id,
        )

    def _is_thread_starter_message(self, message: discord.Message) -> bool:
        if not isinstance(message.channel, discord.Thread):
            return False

        starter_message = getattr(message.channel, "starter_message", None)
        return getattr(starter_message, "id", None) == message.id

    async def _dispatch_response_channel(
        self,
        message: discord.Message,
        *,
        incoming_message: IncomingDiscordMessage,
    ) -> object:
        thread = self._message_thread(message)
        if thread is not None:
            return thread

        if incoming_message.directly_mentions_bot or incoming_message.is_reply_to_bot:
            created_thread = await self._create_thread_for_message(message)
            if created_thread is not None:
                return created_thread

        return self._response_channel(message)

    async def _create_thread_for_message(
        self,
        message: discord.Message,
    ) -> discord.Thread | None:
        create_thread = cast(
            Callable[..., Awaitable[object]] | None,
            getattr(message, "create_thread", None),
        )
        if create_thread is None:
            return None

        try:
            created_thread = await create_thread(name=self._thread_name(message))
        except discord.HTTPException:
            logger.warning(
                "Failed to create thread for Discord message %s",
                message.id,
            )
            return None

        if isinstance(created_thread, discord.Thread):
            return created_thread

        logger.warning(
            "Discord thread creation returned an unexpected channel for message %s",
            message.id,
        )
        return None

    def _thread_name(self, message: discord.Message) -> str:
        return build_thread_title(message.content)

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
