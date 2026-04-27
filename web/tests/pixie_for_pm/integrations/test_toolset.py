from collections.abc import Mapping

import pytest
from langchain_core.tools import BaseTool, StructuredTool

from pixie_for_pm.integrations.toolset import (
    AgentToolset,
    DiscordTriggerContext,
    IntegrationRuntimeProvider,
    IntegrationToolsetInitializer,
)
from pixie_for_pm.web.encryption import CredentialCipher
from pixie_for_pm.web.store import InMemoryConnectionStore

_FERNET_KEY = "j0aN3s-cLScfv0GfNyG8t0UyONn7y8u2s6o6cLs1hYw="


class _RecordingProvider(IntegrationRuntimeProvider):
    def __init__(self) -> None:
        self.calls: list[tuple[dict[str, str], DiscordTriggerContext]] = []
        self.invocations: list[dict[str, object]] = []

    async def load_tools(
        self,
        *,
        credentials: Mapping[str, str],
        trigger: DiscordTriggerContext,
    ) -> tuple[BaseTool, ...]:
        self.calls.append((dict(credentials), trigger))

        async def _get_transcript(transcript_id: str) -> str:
            self.invocations.append({"transcript_id": transcript_id})
            return (
                f"ok:{credentials.get('api_key', 'missing')}:fireflies_get_transcript"
            )

        async def _search(query: str) -> str:
            self.invocations.append({"query": query})
            return f"ok:{credentials.get('access_token', 'missing')}:notion_search"

        if "api_key" in credentials:
            return (
                StructuredTool.from_function(
                    coroutine=_get_transcript,
                    name="fireflies_get_transcript",
                    description="Fetch a Fireflies transcript.",
                ),
                StructuredTool.from_function(
                    coroutine=_search,
                    name="fireflies_search_transcripts",
                    description="Search Fireflies transcripts.",
                ),
            )

        return (
            StructuredTool.from_function(
                coroutine=_get_transcript,
                name="notion_get_page",
                description="Fetch a Notion page.",
            ),
            StructuredTool.from_function(
                coroutine=_search,
                name="notion_search",
                description="Search Notion.",
            ),
        )


@pytest.mark.asyncio
async def test_initializer_builds_langgraph_tools_for_all_connected_integrations() -> (
    None
):
    store = InMemoryConnectionStore()
    cipher = CredentialCipher(_FERNET_KEY)
    notion_provider = _RecordingProvider()
    fireflies_provider = _RecordingProvider()

    server, _ = await store.claim_server("guild-123", "user-1", name="Pixie Guild")
    await store.upsert_connection(
        server.id,
        "notion",
        cipher.encrypt_credentials({"access_token": "notion-token"}),
        scopes=["read_content"],
        status="active",
    )
    await store.upsert_connection(
        server.id,
        "fireflies",
        cipher.encrypt_credentials({"api_key": "fireflies-token"}),
        scopes=None,
        status="active",
    )

    initializer = IntegrationToolsetInitializer(
        store=store,
        cipher=cipher,
        providers={
            "notion": notion_provider,
            "fireflies": fireflies_provider,
        },
    )

    toolset = await initializer.initialize(
        DiscordTriggerContext(
            "guild-123",
            "user-99",
            456,
            "thread-1",
            789,
            "thread-1",
            "direct_bot_mention",
        )
    )

    assert isinstance(toolset, AgentToolset)
    assert [integration.provider_id for integration in toolset.integrations] == [
        "fireflies",
        "notion",
    ]
    assert [tool.name for tool in toolset.as_langgraph_tools()] == [
        "fireflies_get_transcript",
        "fireflies_search_transcripts",
        "notion_get_page",
        "notion_search",
    ]
    assert fireflies_provider.calls[0][0] == {"api_key": "fireflies-token"}
    assert notion_provider.calls[0][0] == {"access_token": "notion-token"}


@pytest.mark.asyncio
async def test_initialized_tool_invocation_passes_credentials_and_updates_last_used() -> (
    None
):
    store = InMemoryConnectionStore()
    cipher = CredentialCipher(_FERNET_KEY)
    notion_provider = _RecordingProvider()

    server, _ = await store.claim_server("guild-456", "user-2")
    await store.upsert_connection(
        server.id,
        "notion",
        cipher.encrypt_credentials({"access_token": "notion-token"}),
        scopes=["read_content"],
        status="active",
    )

    initializer = IntegrationToolsetInitializer(
        store=store,
        cipher=cipher,
        providers={"notion": notion_provider},
    )
    progress_updates: list[str] = []
    toolset = await initializer.initialize(
        DiscordTriggerContext(
            "guild-456",
            "user-22",
            111,
            None,
            222,
            "channel-111-message-222",
            "reply_to_bot",
        ),
        status_emitter=progress_updates.append,
    )

    result = await toolset.tools[1].ainvoke({"query": "roadmap"})
    connection = await store.get_connection(server.id, "notion")

    assert result == "ok:notion-token:notion_search"
    assert len(notion_provider.calls) == 1
    assert notion_provider.calls[0][0] == {"access_token": "notion-token"}
    assert notion_provider.calls[0][1].discord_server_id == "guild-456"
    assert notion_provider.invocations == [{"query": "roadmap"}]
    assert connection is not None
    assert connection.last_used_at is not None
    assert progress_updates == [
        "Fetching data from Notion...",
        "Analyzing results from Notion...",
    ]
