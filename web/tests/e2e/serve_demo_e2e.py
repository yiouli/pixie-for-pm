from __future__ import annotations

import asyncio
from collections.abc import Mapping
from pathlib import Path
from typing import cast

import discord
import uvicorn
from fastapi import APIRouter, FastAPI
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.tools import BaseTool, StructuredTool

from pixie_for_pm.agents.product_designer import build_product_designer_handler
from pixie_for_pm.agents.product_manager import build_product_manager_handler
from pixie_for_pm.agents.registry import AgentHandler
from pixie_for_pm.agents.user_researcher import build_user_researcher_handler
from pixie_for_pm.config.settings import load_settings
from pixie_for_pm.discord.bot import _DiscordProgressReporter
from pixie_for_pm.discord.routing import build_dispatch_request
from pixie_for_pm.domain.models import (
    AgentRole,
    IncomingDiscordMessage,
    OrchestrationResult,
    PublicMessageEmitter,
    ResponseEmitter,
    StatusEmitter,
)
from pixie_for_pm.integrations.toolset import (
    DiscordTriggerContext,
    IntegrationRuntimeProvider,
    IntegrationToolsetInitializer,
)
from pixie_for_pm.orchestration.runtime import PixieOrchestrator
from pixie_for_pm.web.app import create_app
from pixie_for_pm.web.auth import AuthenticatedUser, get_current_user
from pixie_for_pm.web.encryption import CredentialCipher
from pixie_for_pm.web.providers.discord_guilds import (
    DiscordGuild,
    StaticDiscordGuildService,
)
from pixie_for_pm.web.store import InMemoryConnectionStore

E2E_WORKSPACE_ID = "1459772566528069715"
E2E_CHANNEL_ID = 1459772566528069715
E2E_THREAD_ID = "discord-thread-demo-loop-1459772566528069715"
E2E_USER = AuthenticatedUser(
    id="e2e-user-1",
    display_name="Pixie Demo User",
    email="demo@example.com",
)
_FERNET_KEY = "j0aN3s-cLScfv0GfNyG8t0UyONn7y8u2s6o6cLs1hYw="


class _ToolCallingFakeListChatModel(FakeListChatModel):
    def bind_tools(
        self,
        tools: object,
        *,
        tool_choice: object | None = None,
        **kwargs: object,
    ) -> _ToolCallingFakeListChatModel:
        del tools, tool_choice, kwargs
        return self


class _StaticToolProvider(IntegrationRuntimeProvider):
    def __init__(self, tools: tuple[BaseTool, ...]) -> None:
        self._tools = tools

    async def load_tools(
        self,
        *,
        credentials: Mapping[str, str],
        trigger: DiscordTriggerContext,
    ) -> tuple[BaseTool, ...]:
        del credentials, trigger
        return self._tools


def _placeholder_tool(name: str, description: str) -> BaseTool:
    async def _noop(**kwargs: object) -> str:
        del kwargs
        return f"ok:{name}"

    return StructuredTool.from_function(
        coroutine=_noop,
        name=name,
        description=description,
    )


class _E2ESentMessage:
    def __init__(self, content: str) -> None:
        self.content = content
        self.deleted = False

    async def edit(
        self,
        *,
        content: str | None = None,
        embed: object | None = None,
    ) -> _E2ESentMessage:
        del embed
        if content is not None:
            self.content = content
        return self

    async def delete(self) -> None:
        self.deleted = True


class _E2EChannel:
    def __init__(self) -> None:
        self.sent_messages: list[_E2ESentMessage] = []

    async def send(
        self,
        content: str | None = None,
        *,
        embed: object | None = None,
    ) -> _E2ESentMessage:
        del embed
        message = _E2ESentMessage(content or "")
        self.sent_messages.append(message)
        return message

    async def trigger_typing(self) -> None:
        return None


class _E2ESourceMessage:
    def __init__(self, channel: _E2EChannel) -> None:
        self.channel = channel

    async def add_reaction(self, emoji: str) -> None:
        del emoji


def _demo_agent_handlers() -> dict[AgentRole, AgentHandler]:
    return {
        AgentRole.PRODUCT_MANAGER: build_product_manager_handler(
            model=_ToolCallingFakeListChatModel(
                responses=[
                    (
                        "Here are three hypotheses to improve career growth "
                        "feature retention:\n"
                        "1. Clarify the first promotion milestone so users "
                        "know the next win.\n"
                        "2. Add a guided weekly growth loop with commitments, "
                        "check-ins, and momentum cues.\n"
                        "3. Create manager prompts when growth plans stall.\n\n"
                        "I would start with #2. Which direction do you want "
                        "me to deepen?"
                    ),
                    (
                        "Title and thesis\nCareer Growth Weekly Loop\n\n"
                        "Problem statement\nUsers do not form a repeat "
                        "weekly habit around career growth.\n\n"
                        "Goals and non-goals\nIncrease weekly repeat usage "
                        "without adding empty reminder spam."
                    ),
                    "I drafted the PRD for option #2, handed it to design, "
                    "and the designer prepared a clickable Vercel prototype "
                    "focused on the weekly career growth loop. Review the "
                    "prototype flow and tell me what you want changed before "
                    "we move into delivery.",
                ]
            )
        ),
        AgentRole.USER_RESEARCHER: build_user_researcher_handler(
            model=_ToolCallingFakeListChatModel(
                responses=[
                    "Research synthesis: users value the career growth feature "
                    "after the first session, but they lack a repeat weekly "
                    "ritual that makes progress feel visible and worth "
                    "revisiting."
                ]
            )
        ),
        AgentRole.PRODUCT_DESIGNER: build_product_designer_handler(
            model=_ToolCallingFakeListChatModel(
                responses=[
                    "Prototype summary: published a clickable Vercel prototype "
                    "for a weekly career growth loop with a progress rail, "
                    "next-step commitments, and a manager check-in screen."
                ]
            )
        ),
    }


def _build_demo_toolset_initializer(
    *,
    store: InMemoryConnectionStore,
    cipher: CredentialCipher,
) -> IntegrationToolsetInitializer:
    return IntegrationToolsetInitializer(
        store=store,
        cipher=cipher,
        providers={
            "notion": _StaticToolProvider(
                (
                    _placeholder_tool("notion_search", "Search Notion."),
                    _placeholder_tool(
                        "notion_update_content",
                        "Update Notion content.",
                    ),
                )
            ),
            "vercel": _StaticToolProvider(
                (
                    _placeholder_tool(
                        "vercel_list_projects",
                        "List Vercel projects.",
                    ),
                    _placeholder_tool(
                        "vercel_create_deployment",
                        "Create a Vercel deployment.",
                    ),
                )
            ),
        },
    )


async def _run_demo_loop(
    orchestrator: PixieOrchestrator,
    *,
    status_emitter: StatusEmitter | None = None,
    response_emitter: ResponseEmitter | None = None,
    public_message_emitter: PublicMessageEmitter | None = None,
) -> tuple[OrchestrationResult, OrchestrationResult]:
    first_result = await orchestrator.dispatch(
        build_dispatch_request(
            IncomingDiscordMessage(
                discord_message_id=1001,
                discord_server_id=E2E_WORKSPACE_ID,
                channel_id=E2E_CHANNEL_ID,
                thread_id=E2E_THREAD_ID,
                author_id=123,
                content=(
                    "It seems that the career growth feature retention is low, "
                    "what should we build next to improve that?"
                ),
                directly_mentions_bot=True,
                is_reply_to_bot=False,
            )
        ),
        status_emitter=status_emitter,
        response_emitter=response_emitter,
        public_message_emitter=public_message_emitter,
    )
    second_result = await orchestrator.dispatch(
        build_dispatch_request(
            IncomingDiscordMessage(
                discord_message_id=1002,
                discord_server_id=E2E_WORKSPACE_ID,
                channel_id=E2E_CHANNEL_ID,
                thread_id=E2E_THREAD_ID,
                author_id=123,
                content="Can you go deeper on #2?",
                directly_mentions_bot=False,
                is_reply_to_bot=True,
            )
        ),
        status_emitter=status_emitter,
        response_emitter=response_emitter,
        public_message_emitter=public_message_emitter,
    )
    return first_result, second_result


def _build_demo_app() -> FastAPI:
    settings = load_settings(
        {
            "DISCORD_BOT_TOKEN": "discord-token",
            "DISCORD_APPLICATION_ID": "discord-app-id",
            "WEB_APP_URL": "http://127.0.0.1:8010",
            "CREDENTIALS_ENCRYPTION_KEY": _FERNET_KEY,
            "SESSION_SECRET_KEY": _FERNET_KEY,
            "CONNECTION_STORE_SQLITE_PATH": ".state/pixie-e2e-store.sqlite",
            "LANGGRAPH_CHECKPOINT_PATH": ".state/pixie-e2e-langgraph.sqlite",
            "PRODUCT_MANAGER_MODEL": "openai:gpt-5.4",
        }
    )

    store = InMemoryConnectionStore()
    cipher = CredentialCipher(_FERNET_KEY)
    asyncio.run(_seed_demo_store(store, cipher))

    app = create_app(
        settings,
        store=store,
        discord_guild_service=StaticDiscordGuildService(
            guilds={
                E2E_WORKSPACE_ID: DiscordGuild(
                    id=E2E_WORKSPACE_ID,
                    name="Career Growth Demo Lab",
                    icon_url=None,
                )
            }
        ),
    )
    app.dependency_overrides[get_current_user] = lambda: E2E_USER

    router = APIRouter(prefix="/api/e2e", tags=["e2e"])

    @router.post("/demo-loop")
    async def run_demo_loop() -> dict[str, object]:
        toolset_initializer = _build_demo_toolset_initializer(
            store=store,
            cipher=cipher,
        )

        checkpoint_path = Path(".state/pixie-e2e-demo-loop.sqlite")
        if checkpoint_path.exists():
            checkpoint_path.unlink()

        async with PixieOrchestrator(
            checkpoint_path=checkpoint_path,
            agent_handlers=_demo_agent_handlers(),
            toolset_initializer=toolset_initializer,
        ) as orchestrator:
            first_result, second_result = await _run_demo_loop(orchestrator)

        return {
            "discord_server_id": E2E_WORKSPACE_ID,
            "channel_id": E2E_CHANNEL_ID,
            "thread_key": second_result.thread_key,
            "first_turn": [
                {"agent": message.agent.value, "content": message.content}
                for message in first_result.transcript
            ],
            "second_turn": [
                {"agent": message.agent.value, "content": message.content}
                for message in second_result.transcript
            ],
        }

    @router.post("/demo-loop-discord")
    async def run_demo_loop_discord() -> dict[str, object]:
        toolset_initializer = _build_demo_toolset_initializer(
            store=store,
            cipher=cipher,
        )

        checkpoint_path = Path(".state/pixie-e2e-demo-loop-discord.sqlite")
        if checkpoint_path.exists():
            checkpoint_path.unlink()

        response_channel = _E2EChannel()
        reporter = _DiscordProgressReporter(
            source_message=cast(discord.Message, _E2ESourceMessage(response_channel)),
            response_channel=response_channel,
        )

        async with PixieOrchestrator(
            checkpoint_path=checkpoint_path,
            agent_handlers=_demo_agent_handlers(),
            toolset_initializer=toolset_initializer,
        ) as orchestrator:
            await reporter.start()
            try:
                first_result, _ = await _run_demo_loop(
                    orchestrator,
                    status_emitter=reporter.emit,
                    response_emitter=reporter.stream_content,
                    public_message_emitter=reporter.publish_message,
                )
                await reporter.publish_transcript(first_result.transcript)
            finally:
                await reporter.close()

        return {
            "visible_messages": [
                message.content
                for message in response_channel.sent_messages
                if message.content != "" and not message.deleted
            ]
        }

    app.include_router(router)
    return app


async def _seed_demo_store(
    store: InMemoryConnectionStore,
    cipher: CredentialCipher,
) -> None:
    server, _ = await store.claim_server(
        E2E_WORKSPACE_ID,
        E2E_USER.id,
        name="Career Growth Demo Lab",
    )
    await store.upsert_connection(
        server.id,
        "notion",
        cipher.encrypt_credentials({"access_token": "notion-e2e-token"}),
        ["read_content", "update_content"],
        "active",
    )
    await store.upsert_connection(
        server.id,
        "vercel",
        cipher.encrypt_credentials({"access_token": "vercel-e2e-token"}),
        ["projects.write"],
        "active",
    )


app = _build_demo_app()


def main() -> None:
    uvicorn.run(app, host="127.0.0.1", port=8010)


if __name__ == "__main__":
    main()
