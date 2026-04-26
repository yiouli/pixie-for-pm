import pytest

from pixie_for_pm.integrations.toolset import (
    AgentToolset,
    DiscordTriggerContext,
    IntegrationToolCall,
    IntegrationToolsetInitializer,
    McpToolInvoker,
)
from pixie_for_pm.web.encryption import CredentialCipher
from pixie_for_pm.web.store import InMemoryConnectionStore

_FERNET_KEY = "j0aN3s-cLScfv0GfNyG8t0UyONn7y8u2s6o6cLs1hYw="


class _RecordingInvoker(McpToolInvoker):
    def __init__(self) -> None:
        self.calls: list[IntegrationToolCall] = []

    async def invoke(self, call: IntegrationToolCall) -> str:
        self.calls.append(call)
        return f"ok:{call.provider_id}:{call.tool_name}"


@pytest.mark.asyncio
async def test_initializer_builds_langgraph_tools_for_all_connected_integrations() -> (
    None
):
    store = InMemoryConnectionStore()
    cipher = CredentialCipher(_FERNET_KEY)
    invoker = _RecordingInvoker()

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
        invoker=invoker,
    )

    toolset = await initializer.initialize(
        DiscordTriggerContext(
            discord_server_id="guild-123",
            discord_user_id="user-99",
            channel_id=456,
            thread_id="thread-1",
            message_id=789,
            thread_key="thread-1",
            dispatch_reason="direct_bot_mention",
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


@pytest.mark.asyncio
async def test_initialized_tool_invocation_passes_credentials_and_updates_last_used() -> (
    None
):
    store = InMemoryConnectionStore()
    cipher = CredentialCipher(_FERNET_KEY)
    invoker = _RecordingInvoker()

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
        invoker=invoker,
    )
    toolset = await initializer.initialize(
        DiscordTriggerContext(
            discord_server_id="guild-456",
            discord_user_id="user-22",
            channel_id=111,
            thread_id=None,
            message_id=222,
            thread_key="channel-111-message-222",
            dispatch_reason="reply_to_bot",
        )
    )

    result = await toolset.tools[1].ainvoke({"query": "roadmap"})
    connection = await store.get_connection(server.id, "notion")

    assert result == "ok:notion:notion_search"
    assert len(invoker.calls) == 1
    assert invoker.calls[0].provider_id == "notion"
    assert invoker.calls[0].tool_name == "notion_search"
    assert invoker.calls[0].credentials == {"access_token": "notion-token"}
    assert invoker.calls[0].arguments == {"query": "roadmap"}
    assert invoker.calls[0].trigger.discord_server_id == "guild-456"
    assert connection is not None
    assert connection.last_used_at is not None
