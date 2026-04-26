import asyncio
from types import SimpleNamespace
from typing import cast

import discord
import pytest

from pixie_for_pm.config.settings import AppSettings
from pixie_for_pm.discord.bot import PixieDiscordBot, should_dispatch_message
from pixie_for_pm.domain.models import (
    AgentMessage,
    AgentRole,
    DispatchRequest,
    IncomingDiscordMessage,
)


def _message(
    *,
    content: str,
    directly_mentions_bot: bool = False,
    is_reply_to_bot: bool = False,
) -> IncomingDiscordMessage:
    return IncomingDiscordMessage(
        discord_message_id=1,
        discord_server_id="discord-server-1",
        channel_id=2,
        thread_id=None,
        author_id=3,
        content=content,
        directly_mentions_bot=directly_mentions_bot,
        is_reply_to_bot=is_reply_to_bot,
    )


def test_dispatches_when_replying_to_bot_message() -> None:
    message = _message(content="Can you continue that analysis?", is_reply_to_bot=True)

    assert should_dispatch_message(message, bot_user_id=999) is True


def test_dispatches_when_directly_mentioning_the_bot_user() -> None:
    message = _message(
        content="<@999> can you help with roadmap planning?",
        directly_mentions_bot=True,
    )

    assert should_dispatch_message(message, bot_user_id=999) is True


def test_ignores_messages_that_only_look_like_mentions_when_not_normalized() -> None:
    message = _message(content="<@999> can you help with roadmap planning?")

    assert should_dispatch_message(message, bot_user_id=999) is False


def test_ignores_unaddressed_messages() -> None:
    message = _message(content="We should probably revisit onboarding metrics.")

    assert should_dispatch_message(message, bot_user_id=999) is False


@pytest.mark.asyncio
async def test_managed_discord_runtime_keeps_bot_task_running_until_stop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from pixie_for_pm.config.settings import load_settings
    from pixie_for_pm.discord import bot as bot_module

    class FakeDiscordBot:
        latest: "FakeDiscordBot | None" = None

        def __init__(self, settings: AppSettings) -> None:
            self.settings = settings
            self.ready = asyncio.Event()
            self.stopped = asyncio.Event()
            self.was_cancelled = False
            self.close_calls = 0
            FakeDiscordBot.latest = self

        async def start(self, token: str) -> None:
            self.token = token
            self.ready.set()
            try:
                await self.stopped.wait()
            except asyncio.CancelledError:
                self.was_cancelled = True
                raise

        async def wait_until_ready(self) -> None:
            await self.ready.wait()

        async def close(self) -> None:
            self.close_calls += 1
            self.stopped.set()

        def is_closed(self) -> bool:
            return self.stopped.is_set()

    monkeypatch.setattr(bot_module, "PixieDiscordBot", FakeDiscordBot)
    runtime = bot_module.ManagedDiscordRuntime(
        load_settings(
            {
                "DISCORD_BOT_TOKEN": "discord-token",
                "CREDENTIALS_ENCRYPTION_KEY": "j0aN3s-cLScfv0GfNyG8t0UyONn7y8u2s6o6cLs1hYw=",
                "SESSION_SECRET_KEY": "j0aN3s-cLScfv0GfNyG8t0UyONn7y8u2s6o6cLs1hYw=",
            }
        )
    )

    await runtime.start()

    fake_bot = FakeDiscordBot.latest
    assert fake_bot is not None
    assert fake_bot.was_cancelled is False

    await runtime.stop()

    assert fake_bot.close_calls == 1
    assert fake_bot.was_cancelled is False


class _FakeGuild:
    def __init__(self, guild_id: int) -> None:
        self.id = guild_id


class _FakeTree:
    def __init__(self) -> None:
        self.copied_guilds: list[_FakeGuild] = []
        self.sync_calls: list[_FakeGuild | None] = []

    def copy_global_to(self, *, guild: _FakeGuild) -> None:
        self.copied_guilds.append(guild)

    async def sync(self, *, guild: _FakeGuild | None = None) -> None:
        self.sync_calls.append(guild)


class _FakeContextManager:
    def __init__(self) -> None:
        self.enter_calls = 0

    async def __aenter__(self) -> None:
        self.enter_calls += 1


@pytest.mark.asyncio
async def test_setup_hook_enters_orchestrator_without_global_command_sync() -> None:
    orchestrator = _FakeContextManager()
    tree = _FakeTree()
    fake_bot = SimpleNamespace(_orchestrator=orchestrator, tree=tree)

    await PixieDiscordBot.setup_hook(cast(PixieDiscordBot, fake_bot))

    assert orchestrator.enter_calls == 1
    assert tree.sync_calls == []


@pytest.mark.asyncio
async def test_on_ready_syncs_commands_for_each_guild_only_once() -> None:
    guilds = [_FakeGuild(10), _FakeGuild(11)]
    tree = _FakeTree()
    fake_bot = SimpleNamespace(
        _ready_guild_sync_complete=False,
        guilds=guilds,
        tree=tree,
    )

    await PixieDiscordBot.on_ready(cast(PixieDiscordBot, fake_bot))
    await PixieDiscordBot.on_ready(cast(PixieDiscordBot, fake_bot))

    assert fake_bot._ready_guild_sync_complete is True
    assert tree.copied_guilds == guilds
    assert tree.sync_calls == guilds


class _FakeAuthor:
    def __init__(self, author_id: int, *, bot: bool = False) -> None:
        self.id = author_id
        self.bot = bot


class _FakeChannel:
    def __init__(self, channel_id: int) -> None:
        self.id = channel_id
        self.messages: list[str] = []

    async def send(self, content: str) -> None:
        self.messages.append(content)


class _FakeThread(_FakeChannel):
    pass


class _FakeResolvedMessage:
    def __init__(self, *, author_id: int, thread: _FakeThread | None = None) -> None:
        self.author = _FakeAuthor(author_id)
        self.thread = thread


class _FakeReference:
    def __init__(self, resolved: _FakeResolvedMessage) -> None:
        self.resolved = resolved


class _FakeDiscordMessage:
    def __init__(
        self,
        *,
        message_id: int,
        content: str,
        author_id: int,
        channel: _FakeChannel,
        guild_id: int,
        reference: _FakeReference | None = None,
    ) -> None:
        self.id = message_id
        self.content = content
        self.author = _FakeAuthor(author_id)
        self.channel = channel
        self.guild = _FakeGuild(guild_id)
        self.reference = reference
        self.webhook_id = None
        self.reply_messages: list[tuple[str, bool | None]] = []

    async def reply(self, content: str, *, mention_author: bool | None = None) -> None:
        self.reply_messages.append((content, mention_author))


class _FakeOrchestrator:
    def __init__(self) -> None:
        self.requests: list[DispatchRequest] = []

    async def dispatch(self, request: DispatchRequest) -> object:
        self.requests.append(request)
        return SimpleNamespace(
            transcript=[
                AgentMessage(
                    agent=AgentRole.PRODUCT_MANAGER,
                    content="Thread reply from Pixie",
                )
            ]
        )


class _FakeBot:
    def __init__(self, orchestrator: _FakeOrchestrator, *, user_id: int) -> None:
        self.user = SimpleNamespace(id=user_id)
        self._orchestrator = orchestrator

    def _normalize_message(
        self,
        message: discord.Message,
        *,
        bot_user_id: int | None,
    ) -> IncomingDiscordMessage:
        return PixieDiscordBot._normalize_message(
            cast(PixieDiscordBot, self),
            message,
            bot_user_id=bot_user_id,
        )

    def _reply_author_id(self, message: discord.Message) -> int | None:
        return PixieDiscordBot._reply_author_id(
            cast(PixieDiscordBot, self),
            message,
        )

    def _resolved_reply_message(
        self, message: discord.Message
    ) -> discord.Message | None:
        return PixieDiscordBot._resolved_reply_message(
            cast(PixieDiscordBot, self),
            message,
        )

    def _message_thread(self, message: discord.Message) -> discord.Thread | None:
        return PixieDiscordBot._message_thread(
            cast(PixieDiscordBot, self),
            message,
        )

    def _is_reply_to_bot_message(self, message: discord.Message) -> bool:
        return PixieDiscordBot._is_reply_to_bot_message(
            cast(PixieDiscordBot, self),
            message,
        )

    def _response_channel(self, message: discord.Message) -> object:
        return PixieDiscordBot._response_channel(
            cast(PixieDiscordBot, self),
            message,
        )

    async def _publish_transcript(self, *args: object) -> None:
        channel, transcript = args
        await PixieDiscordBot._publish_transcript(
            cast(PixieDiscordBot, self),
            channel,
            cast(list[AgentMessage], transcript),
        )


@pytest.mark.asyncio
async def test_reply_to_thread_starter_reuses_existing_thread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(discord, "Message", _FakeResolvedMessage)
    monkeypatch.setattr(discord, "Thread", _FakeThread)

    thread = _FakeThread(55)
    channel = _FakeChannel(22)
    message = _FakeDiscordMessage(
        message_id=7,
        content="Can you continue in the thread?",
        author_id=42,
        channel=channel,
        guild_id=99,
        reference=_FakeReference(_FakeResolvedMessage(author_id=999, thread=thread)),
    )
    orchestrator = _FakeOrchestrator()
    fake_bot = _FakeBot(orchestrator, user_id=999)

    await PixieDiscordBot.on_message(
        cast(PixieDiscordBot, fake_bot),
        cast(discord.Message, message),
    )

    assert len(orchestrator.requests) == 1
    assert orchestrator.requests[0].message.thread_id == "55"
    assert channel.messages == []
    assert thread.messages == ["Thread reply from Pixie"]


@pytest.mark.asyncio
async def test_reply_to_bot_message_replies_to_source_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(discord, "Message", _FakeResolvedMessage)
    monkeypatch.setattr(discord, "Thread", _FakeThread)

    channel = _FakeChannel(22)
    message = _FakeDiscordMessage(
        message_id=8,
        content="who are you",
        author_id=42,
        channel=channel,
        guild_id=99,
        reference=_FakeReference(_FakeResolvedMessage(author_id=999)),
    )
    orchestrator = _FakeOrchestrator()
    fake_bot = _FakeBot(orchestrator, user_id=999)

    await PixieDiscordBot.on_message(
        cast(PixieDiscordBot, fake_bot),
        cast(discord.Message, message),
    )

    assert len(orchestrator.requests) == 1
    assert channel.messages == []
    assert message.reply_messages == [("Thread reply from Pixie", False)]
