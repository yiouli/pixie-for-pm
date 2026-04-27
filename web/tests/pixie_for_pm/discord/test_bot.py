import asyncio
from collections.abc import Awaitable, Callable
from types import SimpleNamespace
from typing import cast

import discord
import pytest

from pixie_for_pm.config.settings import AppSettings
from pixie_for_pm.discord import bot as bot_module
from pixie_for_pm.discord.bot import (
    PixieDiscordBot,
    _DiscordProgressReporter,
    should_dispatch_message,
)
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
    cleared_globals: list[str] = []

    async def _clear_global_commands() -> None:
        cleared_globals.append("cleared")

    fake_bot = SimpleNamespace(
        _ready_guild_sync_complete=False,
        guilds=guilds,
        tree=tree,
        _clear_global_commands=_clear_global_commands,
    )

    await PixieDiscordBot.on_ready(cast(PixieDiscordBot, fake_bot))
    await PixieDiscordBot.on_ready(cast(PixieDiscordBot, fake_bot))

    assert fake_bot._ready_guild_sync_complete is True
    assert cleared_globals == ["cleared"]
    assert tree.copied_guilds == guilds
    assert tree.sync_calls == guilds


class _FakeAuthor:
    def __init__(self, author_id: int, *, bot: bool = False) -> None:
        self.id = author_id
        self.bot = bot


class _FakeChannel:
    def __init__(self, channel_id: int, *, events: list[str] | None = None) -> None:
        self.id = channel_id
        self.events = events if events is not None else []
        self.messages: list[str] = []
        self.embeds: list[discord.Embed | None] = []
        self.sent_messages: list[_FakeSentMessage] = []

    async def send(
        self,
        content: str | None = None,
        *,
        embed: discord.Embed | None = None,
    ) -> "_FakeSentMessage":
        self.events.append("send")
        self.messages.append(content or "")
        self.embeds.append(embed)
        sent_message = _FakeSentMessage(content or "", embed=embed)
        self.sent_messages.append(sent_message)
        return sent_message

    async def trigger_typing(self) -> None:
        self.events.append("typing-indicator")

    def typing(self) -> object:
        return _FakeTypingContext(self.events)


class _FakeThread(_FakeChannel):
    def __init__(
        self,
        channel_id: int,
        *,
        name: str | None = None,
        events: list[str] | None = None,
        history_messages: list[object] | None = None,
        starter_message: object | None = None,
    ) -> None:
        super().__init__(channel_id, events=events)
        self.name = name
        self._history_messages = (
            history_messages if history_messages is not None else []
        )
        self.starter_message = starter_message

    def history(self, *, limit: int = 25) -> object:
        del limit

        async def _iterator() -> object:
            for history_message in self._history_messages:
                yield history_message

        return _iterator()


class _FakeTypingContext:
    def __init__(self, events: list[str]) -> None:
        self._events = events

    async def __aenter__(self) -> None:
        self._events.append("typing-indicator")

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        del exc_type, exc, tb


class _FakeTypingOnlyChannel:
    def __init__(self, channel_id: int, *, events: list[str] | None = None) -> None:
        self.id = channel_id
        self.events = events if events is not None else []
        self.messages: list[str] = []
        self.embeds: list[discord.Embed | None] = []
        self.sent_messages: list[_FakeSentMessage] = []

    async def send(
        self,
        content: str | None = None,
        *,
        embed: discord.Embed | None = None,
    ) -> "_FakeSentMessage":
        self.events.append("send")
        self.messages.append(content or "")
        self.embeds.append(embed)
        sent_message = _FakeSentMessage(content or "", embed=embed)
        self.sent_messages.append(sent_message)
        return sent_message

    def typing(self) -> object:
        return _FakeTypingContext(self.events)


class _FakeSentMessage:
    def __init__(self, content: str, *, embed: discord.Embed | None = None) -> None:
        self.content = content
        self.embed = embed
        self.edits: list[str] = []
        self.embed_edits: list[discord.Embed] = []
        self.deleted = False

    async def edit(
        self,
        *,
        content: str | None = None,
        embed: discord.Embed | None = None,
    ) -> "_FakeSentMessage":
        if content is not None:
            self.content = content
            self.edits.append(content)
        if embed is not None:
            self.embed = embed
            self.embed_edits.append(embed)
        return self

    async def delete(self) -> None:
        self.deleted = True


class _FakeResolvedMessage:
    def __init__(self, *, author_id: int, thread: _FakeThread | None = None) -> None:
        self.author = _FakeAuthor(author_id)
        self.thread = thread


class _FakeThreadHistoryMessage:
    def __init__(self, *, message_id: int, author_id: int, bot: bool = False) -> None:
        self.id = message_id
        self.author = _FakeAuthor(author_id, bot=bot)


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
        events: list[str] | None = None,
    ) -> None:
        self.id = message_id
        self.content = content
        self.author = _FakeAuthor(author_id)
        self.channel = channel
        self.guild = _FakeGuild(guild_id)
        self.reference = reference
        self.webhook_id = None
        self.events = events if events is not None else []
        self.reactions: list[str] = []
        self.reply_messages: list[tuple[str, bool | None]] = []
        self.reply_sent_messages: list[_FakeSentMessage] = []
        self.created_threads: list[_FakeThread] = []
        self.created_thread_names: list[str] = []

    async def add_reaction(self, emoji: str) -> None:
        self.events.append("reaction")
        self.reactions.append(emoji)

    async def reply(
        self,
        content: str | None = None,
        *,
        mention_author: bool | None = None,
        embed: discord.Embed | None = None,
    ) -> _FakeSentMessage:
        self.events.append("reply")
        self.reply_messages.append((content or "", mention_author))
        sent_message = _FakeSentMessage(content or "", embed=embed)
        self.reply_sent_messages.append(sent_message)
        return sent_message

    async def create_thread(
        self,
        *,
        name: str,
        auto_archive_duration: int | None = None,
    ) -> _FakeThread:
        del auto_archive_duration
        self.events.append("create-thread")
        self.created_thread_names.append(name)
        thread = _FakeThread(
            self.id + 1000,
            name=name,
            events=self.events,
            starter_message=self,
        )
        self.created_threads.append(thread)
        return thread


class _FakeOrchestrator:
    def __init__(
        self,
        *,
        events: list[str] | None = None,
        error: Exception | None = None,
        transcript: list[AgentMessage] | None = None,
        response_deltas: list[str] | None = None,
    ) -> None:
        self.requests: list[DispatchRequest] = []
        self.events = events if events is not None else []
        self.status_updates: list[str] = []
        self.error = error
        self.response_deltas = response_deltas or []
        self.transcript = transcript or [
            AgentMessage(
                agent=AgentRole.PRODUCT_MANAGER,
                content="Thread reply from Pixie",
            )
        ]

    async def dispatch(
        self,
        request: DispatchRequest,
        *,
        status_emitter: Callable[[str], Awaitable[None]] | None = None,
        response_emitter: Callable[[str], Awaitable[None]] | None = None,
    ) -> object:
        self.requests.append(request)
        self.events.append("dispatch")
        if status_emitter is not None:
            await status_emitter("Analyzing request...")
            self.status_updates.append("Analyzing request...")
        if response_emitter is not None:
            for delta in self.response_deltas:
                await response_emitter(delta)
        if self.error is not None:
            raise self.error
        return SimpleNamespace(transcript=self.transcript)


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

    async def _dispatch_response_channel(
        self,
        message: discord.Message,
        *,
        incoming_message: IncomingDiscordMessage,
    ) -> object:
        return await PixieDiscordBot._dispatch_response_channel(
            cast(PixieDiscordBot, self),
            message,
            incoming_message=incoming_message,
        )

    async def _create_thread_for_message(
        self,
        message: discord.Message,
    ) -> discord.Thread | None:
        return await PixieDiscordBot._create_thread_for_message(
            cast(PixieDiscordBot, self),
            message,
        )

    def _thread_name(self, message: discord.Message) -> str:
        return PixieDiscordBot._thread_name(
            cast(PixieDiscordBot, self),
            message,
        )

    def _is_thread_starter_message(self, message: discord.Message) -> bool:
        return PixieDiscordBot._is_thread_starter_message(
            cast(PixieDiscordBot, self),
            message,
        )

    async def _thread_has_bot_context(self, message: discord.Message) -> bool:
        return await PixieDiscordBot._thread_has_bot_context(
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

    events: list[str] = []
    thread = _FakeThread(55, events=events)
    channel = _FakeChannel(22, events=events)
    message = _FakeDiscordMessage(
        message_id=7,
        content="Can you continue in the thread?",
        author_id=42,
        channel=channel,
        guild_id=99,
        reference=_FakeReference(_FakeResolvedMessage(author_id=999, thread=thread)),
        events=events,
    )
    orchestrator = _FakeOrchestrator(events=events)
    fake_bot = _FakeBot(orchestrator, user_id=999)

    await PixieDiscordBot.on_message(
        cast(PixieDiscordBot, fake_bot),
        cast(discord.Message, message),
    )

    assert len(orchestrator.requests) == 1
    assert orchestrator.requests[0].message.thread_id == "55"
    assert channel.messages == []
    assert message.reactions == ["\N{EYES}"]
    assert events[0] == "reaction"
    assert "send" in events
    assert "dispatch" in events
    assert thread.messages == ["", "Thread reply from Pixie"]
    assert thread.sent_messages[0].embed_edits[-1].description == "Analyzing request..."
    assert thread.sent_messages[1].content == "Thread reply from Pixie"


@pytest.mark.asyncio
async def test_direct_mention_creates_thread_and_replies_in_thread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(discord, "Message", _FakeResolvedMessage)
    monkeypatch.setattr(discord, "Thread", _FakeThread)

    events: list[str] = []
    channel = _FakeChannel(22, events=events)
    message = _FakeDiscordMessage(
        message_id=11,
        content="<@999> can you expand this?",
        author_id=42,
        channel=channel,
        guild_id=99,
        events=events,
    )
    orchestrator = _FakeOrchestrator(events=events)
    fake_bot = _FakeBot(orchestrator, user_id=999)

    await PixieDiscordBot.on_message(
        cast(PixieDiscordBot, fake_bot),
        cast(discord.Message, message),
    )

    assert len(orchestrator.requests) == 1
    assert len(message.created_threads) == 1
    assert message.created_thread_names == ["expand this"]
    created_thread = message.created_threads[0]
    assert orchestrator.requests[0].message.thread_id == str(created_thread.id)
    assert channel.messages == []
    assert message.reply_messages == []
    assert created_thread.messages == ["", "Thread reply from Pixie"]
    assert created_thread.sent_messages[1].content == "Thread reply from Pixie"


@pytest.mark.asyncio
async def test_progress_reporter_uses_typing_context_when_trigger_typing_missing() -> (
    None
):
    events: list[str] = []
    source_message = _FakeDiscordMessage(
        message_id=13,
        content="status",
        author_id=42,
        channel=_FakeChannel(22, events=events),
        guild_id=99,
        events=events,
    )
    response_channel = _FakeTypingOnlyChannel(55, events=events)
    reporter = _DiscordProgressReporter(
        source_message=cast(discord.Message, source_message),
        response_channel=response_channel,
    )

    await reporter._trigger_typing_once()

    assert events == ["typing-indicator"]


@pytest.mark.asyncio
async def test_progress_reporter_renders_status_updates_as_in_progress_embed() -> None:
    events: list[str] = []
    source_message = _FakeDiscordMessage(
        message_id=16,
        content="status",
        author_id=42,
        channel=_FakeChannel(22, events=events),
        guild_id=99,
        events=events,
    )
    response_channel = _FakeChannel(55, events=events)
    reporter = _DiscordProgressReporter(
        source_message=cast(discord.Message, source_message),
        response_channel=response_channel,
    )

    await reporter.start()
    await reporter.emit("Analyzing request...")

    status_message = response_channel.sent_messages[0]
    assert status_message.content == ""
    assert status_message.embed is not None
    assert status_message.embed.title == "Pixie is working"
    assert status_message.embed.description == "Analyzing request..."
    assert status_message.embed.colour == discord.Colour.orange()
    assert status_message.embed_edits[-1].description == "Analyzing request..."


@pytest.mark.asyncio
async def test_progress_reporter_refreshes_typing_after_non_final_output() -> None:
    events: list[str] = []
    source_message = _FakeDiscordMessage(
        message_id=17,
        content="status",
        author_id=42,
        channel=_FakeChannel(22, events=events),
        guild_id=99,
        events=events,
    )
    response_channel = _FakeChannel(55, events=events)
    reporter = _DiscordProgressReporter(
        source_message=cast(discord.Message, source_message),
        response_channel=response_channel,
    )

    original_interval = bot_module.DISCORD_STREAM_UPDATE_INTERVAL
    bot_module.DISCORD_STREAM_UPDATE_INTERVAL = 40
    try:
        await reporter.emit("Thinking...")
        assert events[-2:] == ["send", "typing-indicator"]

        await reporter.stream_content("A" * 60)
        assert events[-2:] == ["send", "typing-indicator"]
    finally:
        bot_module.DISCORD_STREAM_UPDATE_INTERVAL = original_interval


@pytest.mark.asyncio
async def test_progress_reporter_splits_responses_at_the_default_stream_chunk_size() -> (
    None
):
    events: list[str] = []
    source_message = _FakeDiscordMessage(
        message_id=18,
        content="status",
        author_id=42,
        channel=_FakeChannel(22, events=events),
        guild_id=99,
        events=events,
    )
    response_channel = _FakeChannel(55, events=events)
    reporter = _DiscordProgressReporter(
        source_message=cast(discord.Message, source_message),
        response_channel=response_channel,
    )
    natural_break = "A" * 488
    transcript = [
        AgentMessage(
            agent=AgentRole.PRODUCT_MANAGER,
            content=f"{natural_break}.\n\nSecond chunk starts here.",
        )
    ]

    await reporter.start()
    await reporter.publish_transcript(transcript)

    assert len(response_channel.sent_messages) == 3
    assert response_channel.sent_messages[1].content == f"{natural_break}."
    assert len(response_channel.sent_messages[1].content) <= 500
    assert response_channel.sent_messages[2].content == "Second chunk starts here."


@pytest.mark.asyncio
async def test_progress_reporter_streams_partial_content_before_final_publish() -> None:
    events: list[str] = []
    source_message = _FakeDiscordMessage(
        message_id=19,
        content="status",
        author_id=42,
        channel=_FakeChannel(22, events=events),
        guild_id=99,
        events=events,
    )
    response_channel = _FakeChannel(55, events=events)
    reporter = _DiscordProgressReporter(
        source_message=cast(discord.Message, source_message),
        response_channel=response_channel,
    )

    await reporter.start()
    await reporter.stream_content("A" * 300)
    await reporter.stream_content("B" * 300)

    status_message = response_channel.sent_messages[0]
    assert len(response_channel.sent_messages) == 2
    assert status_message.content == ""
    assert status_message.edits == []
    assert response_channel.sent_messages[1].content == ("A" * 300) + ("B" * 200)

    await reporter.publish_transcript(
        [
            AgentMessage(
                agent=AgentRole.PRODUCT_MANAGER,
                content=("A" * 300) + ("B" * 300),
            )
        ]
    )

    assert len(response_channel.sent_messages) == 3
    assert response_channel.sent_messages[1].content == ("A" * 300) + ("B" * 200)
    assert response_channel.sent_messages[2].content == ("B" * 100)
    assert status_message.deleted is True


@pytest.mark.asyncio
async def test_progress_reporter_rolls_over_to_follow_up_while_streaming() -> None:
    events: list[str] = []
    source_message = _FakeDiscordMessage(
        message_id=20,
        content="status",
        author_id=42,
        channel=_FakeChannel(22, events=events),
        guild_id=99,
        events=events,
    )
    response_channel = _FakeChannel(55, events=events)
    reporter = _DiscordProgressReporter(
        source_message=cast(discord.Message, source_message),
        response_channel=response_channel,
    )

    original_limit = bot_module.DISCORD_MESSAGE_LIMIT
    bot_module.DISCORD_MESSAGE_LIMIT = 80
    try:
        await reporter.start()
        await reporter.stream_content(
            "First section stays together and ends cleanly.\n\n"
        )
        await reporter.stream_content(
            "Second section keeps streaming with more detail than fits in one chunk."
        )

        assert len(response_channel.sent_messages) == 2
        assert response_channel.sent_messages[1].content == (
            "First section stays together and ends cleanly."
        )
        await reporter.publish_transcript(
            [
                AgentMessage(
                    agent=AgentRole.PRODUCT_MANAGER,
                    content=(
                        "First section stays together and ends cleanly.\n\n"
                        "Second section keeps streaming with more detail than fits in one chunk."
                    ),
                )
            ]
        )
        assert len(response_channel.sent_messages) == 3
        assert response_channel.sent_messages[2].content.startswith("Second section")
    finally:
        bot_module.DISCORD_MESSAGE_LIMIT = original_limit


@pytest.mark.asyncio
async def test_progress_reporter_flushes_stream_at_clean_break_within_chunk_size() -> (
    None
):
    events: list[str] = []
    source_message = _FakeDiscordMessage(
        message_id=21,
        content="status",
        author_id=42,
        channel=_FakeChannel(22, events=events),
        guild_id=99,
        events=events,
    )
    response_channel = _FakeChannel(55, events=events)
    reporter = _DiscordProgressReporter(
        source_message=cast(discord.Message, source_message),
        response_channel=response_channel,
    )

    original_interval = bot_module.DISCORD_STREAM_UPDATE_INTERVAL
    original_limit = bot_module.DISCORD_MESSAGE_LIMIT
    bot_module.DISCORD_STREAM_UPDATE_INTERVAL = 40
    bot_module.DISCORD_MESSAGE_LIMIT = 2000
    try:
        await reporter.start()
        await reporter.stream_content(
            "First sentence ends here. Second sentence keeps going afterward."
        )

        assert len(response_channel.sent_messages) == 2
        assert response_channel.sent_messages[1].content == "First sentence ends here."

        await reporter.publish_transcript(
            [
                AgentMessage(
                    agent=AgentRole.PRODUCT_MANAGER,
                    content=(
                        "First sentence ends here. "
                        "Second sentence keeps going afterward."
                    ),
                )
            ]
        )

        assert len(response_channel.sent_messages) == 3
        assert response_channel.sent_messages[2].content == (
            "Second sentence keeps going afterward."
        )
    finally:
        bot_module.DISCORD_STREAM_UPDATE_INTERVAL = original_interval
        bot_module.DISCORD_MESSAGE_LIMIT = original_limit


@pytest.mark.asyncio
async def test_progress_reporter_renders_markdown_tables_for_discord() -> None:
    events: list[str] = []
    source_message = _FakeDiscordMessage(
        message_id=22,
        content="status",
        author_id=42,
        channel=_FakeChannel(22, events=events),
        guild_id=99,
        events=events,
    )
    response_channel = _FakeChannel(55, events=events)
    reporter = _DiscordProgressReporter(
        source_message=cast(discord.Message, source_message),
        response_channel=response_channel,
    )

    await reporter.start()
    await reporter.publish_transcript(
        [
            AgentMessage(
                agent=AgentRole.PRODUCT_MANAGER,
                content=(
                    "Shortlist:\n\n"
                    "| Player | Category |\n"
                    "| --- | --- |\n"
                    "| LangSmith | Observability |\n"
                    "| Braintrust | Evals |"
                ),
            )
        ]
    )

    assert len(response_channel.sent_messages) == 2
    rendered_content = response_channel.sent_messages[1].content
    assert rendered_content.startswith("Shortlist:\n\n```text\n")
    assert "Player" in rendered_content
    assert "LangSmith" in rendered_content
    assert "Braintrust" in rendered_content
    assert "| --- | --- |" not in rendered_content
    assert rendered_content.endswith("\n```")


@pytest.mark.asyncio
async def test_direct_mention_thread_starter_echo_is_ignored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(discord, "Message", _FakeResolvedMessage)
    monkeypatch.setattr(discord, "Thread", _FakeThread)

    events: list[str] = []
    channel = _FakeChannel(22, events=events)
    message = _FakeDiscordMessage(
        message_id=12,
        content="<@999> can you expand this?",
        author_id=42,
        channel=channel,
        guild_id=99,
        events=events,
    )
    orchestrator = _FakeOrchestrator(events=events)
    fake_bot = _FakeBot(orchestrator, user_id=999)

    await PixieDiscordBot.on_message(
        cast(PixieDiscordBot, fake_bot),
        cast(discord.Message, message),
    )

    created_thread = message.created_threads[0]
    echoed_message = _FakeDiscordMessage(
        message_id=12,
        content="<@999> can you expand this?",
        author_id=42,
        channel=created_thread,
        guild_id=99,
        events=events,
    )

    await PixieDiscordBot.on_message(
        cast(PixieDiscordBot, fake_bot),
        cast(discord.Message, echoed_message),
    )

    assert len(orchestrator.requests) == 1
    assert created_thread.messages == ["", "Thread reply from Pixie"]
    assert len(created_thread.sent_messages) == 2


@pytest.mark.asyncio
async def test_reply_to_bot_message_creates_thread_and_replies_in_thread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(discord, "Message", _FakeResolvedMessage)
    monkeypatch.setattr(discord, "Thread", _FakeThread)

    events: list[str] = []
    channel = _FakeChannel(22, events=events)
    message = _FakeDiscordMessage(
        message_id=8,
        content="who are you",
        author_id=42,
        channel=channel,
        guild_id=99,
        reference=_FakeReference(_FakeResolvedMessage(author_id=999)),
        events=events,
    )
    orchestrator = _FakeOrchestrator(events=events)
    fake_bot = _FakeBot(orchestrator, user_id=999)

    await PixieDiscordBot.on_message(
        cast(PixieDiscordBot, fake_bot),
        cast(discord.Message, message),
    )

    assert len(orchestrator.requests) == 1
    assert channel.messages == []
    assert message.reactions == ["\N{EYES}"]
    assert "reaction" in events
    assert "create-thread" in events
    assert "dispatch" in events
    assert message.reply_messages == []
    assert len(message.created_threads) == 1
    created_thread = message.created_threads[0]
    assert orchestrator.requests[0].message.thread_id == str(created_thread.id)
    assert created_thread.messages == ["", "Thread reply from Pixie"]
    assert (
        created_thread.sent_messages[0].embed_edits[-1].description
        == "Analyzing request..."
    )
    assert created_thread.sent_messages[1].content == "Thread reply from Pixie"


@pytest.mark.asyncio
async def test_long_transcript_is_split_across_messages_at_natural_breaks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(discord, "Message", _FakeResolvedMessage)
    monkeypatch.setattr(discord, "Thread", _FakeThread)
    monkeypatch.setattr(bot_module, "DISCORD_MESSAGE_LIMIT", 80)

    events: list[str] = []
    channel = _FakeChannel(22, events=events)
    message = _FakeDiscordMessage(
        message_id=14,
        content="<@999> can you summarize this?",
        author_id=42,
        channel=channel,
        guild_id=99,
        events=events,
    )
    long_reply = (
        "First section stays together and ends cleanly.\n\n"
        "Second section should show up in a follow-up message."
    )
    orchestrator = _FakeOrchestrator(
        events=events,
        transcript=[
            AgentMessage(
                agent=AgentRole.PRODUCT_MANAGER,
                content=long_reply,
            )
        ],
    )
    fake_bot = _FakeBot(orchestrator, user_id=999)

    await PixieDiscordBot.on_message(
        cast(PixieDiscordBot, fake_bot),
        cast(discord.Message, message),
    )

    created_thread = message.created_threads[0]
    first_reply = created_thread.sent_messages[1]
    second_reply = created_thread.sent_messages[2]
    assert len(first_reply.content) <= 80
    assert first_reply.content == "First section stays together and ends cleanly."
    assert "Second section" not in first_reply.content
    assert second_reply.content.startswith("Second section")


@pytest.mark.asyncio
async def test_dispatch_failure_uses_styled_error_embed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(discord, "Message", _FakeResolvedMessage)
    monkeypatch.setattr(discord, "Thread", _FakeThread)

    events: list[str] = []
    channel = _FakeChannel(22, events=events)
    message = _FakeDiscordMessage(
        message_id=15,
        content="who are you",
        author_id=42,
        channel=channel,
        guild_id=99,
        reference=_FakeReference(_FakeResolvedMessage(author_id=999)),
        events=events,
    )
    orchestrator = _FakeOrchestrator(
        events=events,
        error=RuntimeError("agent backend failed"),
    )
    fake_bot = _FakeBot(orchestrator, user_id=999)

    await PixieDiscordBot.on_message(
        cast(PixieDiscordBot, fake_bot),
        cast(discord.Message, message),
    )

    created_thread = message.created_threads[0]
    error_embed = created_thread.sent_messages[0].embed_edits[-1]
    assert error_embed.title == "Pixie couldn't complete that request"
    assert error_embed.description == "Error: Pixie failed to complete this request."
    assert error_embed.colour == discord.Colour.red()


@pytest.mark.asyncio
async def test_thread_message_dispatches_when_thread_already_contains_bot_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(discord, "Message", _FakeResolvedMessage)
    monkeypatch.setattr(discord, "Thread", _FakeThread)

    events: list[str] = []
    thread = _FakeThread(
        55,
        events=events,
        history_messages=[
            _FakeThreadHistoryMessage(message_id=1, author_id=999, bot=True),
            _FakeThreadHistoryMessage(message_id=2, author_id=42),
        ],
    )
    message = _FakeDiscordMessage(
        message_id=9,
        content="continue the plan",
        author_id=42,
        channel=thread,
        guild_id=99,
        events=events,
    )
    orchestrator = _FakeOrchestrator(events=events)
    fake_bot = _FakeBot(orchestrator, user_id=999)

    await PixieDiscordBot.on_message(
        cast(PixieDiscordBot, fake_bot),
        cast(discord.Message, message),
    )

    assert len(orchestrator.requests) == 1
    assert orchestrator.requests[0].message.thread_id == "55"
    assert message.reactions == ["\N{EYES}"]
    assert thread.messages == ["", "Thread reply from Pixie"]
    assert thread.sent_messages[1].content == "Thread reply from Pixie"


@pytest.mark.asyncio
async def test_dispatch_failure_edits_status_message_to_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(discord, "Message", _FakeResolvedMessage)
    monkeypatch.setattr(discord, "Thread", _FakeThread)

    events: list[str] = []
    channel = _FakeChannel(22, events=events)
    message = _FakeDiscordMessage(
        message_id=10,
        content="who are you",
        author_id=42,
        channel=channel,
        guild_id=99,
        reference=_FakeReference(_FakeResolvedMessage(author_id=999)),
        events=events,
    )
    orchestrator = _FakeOrchestrator(
        events=events,
        error=RuntimeError("agent backend failed"),
    )
    fake_bot = _FakeBot(orchestrator, user_id=999)

    await PixieDiscordBot.on_message(
        cast(PixieDiscordBot, fake_bot),
        cast(discord.Message, message),
    )

    assert len(orchestrator.requests) == 1
    assert message.reply_messages == []
    assert len(message.created_threads) == 1
    created_thread = message.created_threads[0]
    assert created_thread.messages == [""]
    assert created_thread.sent_messages[0].edits[-1] == ""
    error_embed = created_thread.sent_messages[0].embed_edits[-1]
    assert error_embed.title == "Pixie couldn't complete that request"
    assert error_embed.description == "Error: Pixie failed to complete this request."
