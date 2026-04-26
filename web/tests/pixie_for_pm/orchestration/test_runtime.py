from pathlib import Path

import pytest

from pixie_for_pm.agents.registry import AgentHandler
from pixie_for_pm.discord.routing import build_dispatch_request
from pixie_for_pm.domain.models import (
    AgentExecution,
    AgentHandoff,
    AgentMessage,
    AgentRole,
    IncomingDiscordMessage,
    WorkflowContext,
)
from pixie_for_pm.integrations.toolset import (
    AgentToolset,
    ConnectedIntegration,
    DiscordTriggerContext,
    ToolsetInitializer,
)
from pixie_for_pm.orchestration.runtime import PixieOrchestrator


async def _pm_with_handoff(context: WorkflowContext) -> AgentExecution:
    return AgentExecution(
        messages=[
            AgentMessage(
                agent=AgentRole.PRODUCT_MANAGER,
                content=f"Placeholder planning response for: {context.user_message}",
            )
        ],
        handoffs=[
            AgentHandoff(
                source_agent=AgentRole.PRODUCT_MANAGER,
                target_agent=AgentRole.MARKET_ANALYST,
                reason="Need a market sizing pass before drafting the PRD.",
            )
        ],
    )


async def _market_placeholder(context: WorkflowContext) -> AgentExecution:
    return AgentExecution(
        messages=[
            AgentMessage(
                agent=AgentRole.MARKET_ANALYST,
                content=f"Placeholder market analysis response for: {context.user_message}",
            )
        ]
    )


class _StaticToolsetInitializer(ToolsetInitializer):
    def __init__(self, toolset: AgentToolset) -> None:
        self.toolset = toolset
        self.calls: list[DiscordTriggerContext] = []

    async def initialize(self, trigger: DiscordTriggerContext) -> AgentToolset:
        self.calls.append(trigger)
        return self.toolset


async def _assert_tool_context(context: WorkflowContext) -> AgentExecution:
    assert context.trigger.discord_server_id == "discord-server-789"
    assert context.trigger.discord_user_id == "31"
    assert [
        integration.provider_id for integration in context.toolset.integrations
    ] == ["notion"]
    assert context.toolset.as_langgraph_tools() == context.toolset.tools
    return AgentExecution(
        messages=[
            AgentMessage(
                agent=AgentRole.PRODUCT_MANAGER,
                content="Tool-aware placeholder response",
            )
        ]
    )


@pytest.mark.asyncio
async def test_orchestrator_runs_placeholder_agent_and_persists_sqlite_checkpoint(
    tmp_path: Path,
) -> None:
    request = build_dispatch_request(
        IncomingDiscordMessage(
            discord_message_id=10,
            discord_server_id="discord-server-123",
            channel_id=20,
            thread_id="discord-thread-123",
            author_id=30,
            content="Help me frame a PM agent product strategy.",
            directly_mentions_bot=True,
            is_reply_to_bot=False,
        )
    )

    async with PixieOrchestrator(
        checkpoint_path=tmp_path / "pixie.sqlite"
    ) as orchestrator:
        result = await orchestrator.dispatch(request)

    assert (tmp_path / "pixie.sqlite").exists()
    assert [message.agent for message in result.transcript] == [
        AgentRole.PRODUCT_MANAGER
    ]
    assert "placeholder" in result.transcript[0].content.lower()


@pytest.mark.asyncio
async def test_orchestrator_keeps_handoffs_out_of_the_public_transcript(
    tmp_path: Path,
) -> None:
    handlers: dict[AgentRole, AgentHandler] = {
        AgentRole.PRODUCT_MANAGER: _pm_with_handoff,
        AgentRole.MARKET_ANALYST: _market_placeholder,
    }
    request = build_dispatch_request(
        IncomingDiscordMessage(
            discord_message_id=11,
            discord_server_id="discord-server-456",
            channel_id=21,
            thread_id="discord-thread-456",
            author_id=31,
            content="Is this market large enough for a vertical product?",
            directly_mentions_bot=True,
            is_reply_to_bot=False,
        )
    )

    async with PixieOrchestrator(
        checkpoint_path=tmp_path / "handoff.sqlite",
        agent_handlers=handlers,
    ) as orchestrator:
        result = await orchestrator.dispatch(request)

    assert [message.agent for message in result.transcript] == [
        AgentRole.PRODUCT_MANAGER,
        AgentRole.MARKET_ANALYST,
    ]
    assert all(
        "handoff" not in message.content.lower() for message in result.transcript
    )


@pytest.mark.asyncio
async def test_orchestrator_initializes_request_scoped_toolset_for_agent_context(
    tmp_path: Path,
) -> None:
    request = build_dispatch_request(
        IncomingDiscordMessage(
            discord_message_id=12,
            discord_server_id="discord-server-789",
            channel_id=22,
            thread_id="discord-thread-789",
            author_id=31,
            content="Can you use our connected tools?",
            directly_mentions_bot=True,
            is_reply_to_bot=False,
        )
    )
    initializer = _StaticToolsetInitializer(
        AgentToolset(
            tools=(),
            integrations=(
                ConnectedIntegration(
                    provider_id="notion",
                    provider_name="Notion",
                    auth_type="oauth2",
                    status="active",
                    scopes=("read_content",),
                    tool_names=("notion_search", "notion_get_page"),
                ),
            ),
        )
    )

    async with PixieOrchestrator(
        checkpoint_path=tmp_path / "tool-context.sqlite",
        agent_handlers={AgentRole.PRODUCT_MANAGER: _assert_tool_context},
        toolset_initializer=initializer,
    ) as orchestrator:
        result = await orchestrator.dispatch(request)

    assert [message.content for message in result.transcript] == [
        "Tool-aware placeholder response"
    ]
    assert [trigger.discord_server_id for trigger in initializer.calls] == [
        "discord-server-789"
    ]
