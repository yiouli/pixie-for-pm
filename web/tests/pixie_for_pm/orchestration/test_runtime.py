from pathlib import Path

import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel

from pixie_for_pm.agents.registry import AgentHandler, build_product_manager_handler
from pixie_for_pm.discord.routing import build_dispatch_request
from pixie_for_pm.domain.models import (
    AgentExecution,
    AgentHandoff,
    AgentMessage,
    AgentRole,
    DispatchRequest,
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


class _ToolCallingFakeListChatModel(FakeListChatModel):
    def bind_tools(
        self,
        tools: object,
        *,
        tool_choice: object | None = None,
        **kwargs: object,
    ) -> "_ToolCallingFakeListChatModel":
        del tools, tool_choice, kwargs
        return self


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


async def _pm_direct_response(context: WorkflowContext) -> AgentExecution:
    return AgentExecution(
        messages=[
            AgentMessage(
                agent=AgentRole.PRODUCT_MANAGER,
                content=f"PM direct response for: {context.user_message}",
            )
        ]
    )


async def _invalid_dispatcher_handoff(context: WorkflowContext) -> AgentExecution:
    return AgentExecution(
        messages=[],
        handoffs=[
            AgentHandoff(
                source_agent=AgentRole.PRODUCT_MANAGER,
                target_agent=AgentRole.DISPATCHER,
                reason="Attempting to re-dispatch.",
            )
        ],
    )


class _StaticToolsetInitializer(ToolsetInitializer):
    def __init__(self, toolset: AgentToolset) -> None:
        self.toolset = toolset
        self.calls: list[DiscordTriggerContext] = []

    async def initialize(
        self,
        trigger: DiscordTriggerContext,
        *,
        status_emitter: object | None = None,
    ) -> AgentToolset:
        del status_emitter
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
async def test_orchestrator_runs_product_manager_deep_agent_and_persists_sqlite_checkpoint(
    tmp_path: Path,
) -> None:
    request = DispatchRequest(
        message=IncomingDiscordMessage(
            discord_message_id=10,
            discord_server_id="discord-server-123",
            channel_id=20,
            thread_id="discord-thread-123",
            author_id=30,
            content="Help me frame a PM agent product strategy.",
            directly_mentions_bot=True,
            is_reply_to_bot=False,
        ),
        target_agent=AgentRole.PRODUCT_MANAGER,
        reason="direct_bot_mention",
    )

    async with PixieOrchestrator(
        checkpoint_path=tmp_path / "pixie.sqlite",
        agent_handlers={
            AgentRole.PRODUCT_MANAGER: build_product_manager_handler(
                model=_ToolCallingFakeListChatModel(
                    responses=[
                        "PM_AGENT_OK Product strategy memo: prioritize onboarding, "
                        "activation, and weekly retained teams."
                    ]
                )
            )
        },
    ) as orchestrator:
        result = await orchestrator.dispatch(request)

    assert (tmp_path / "pixie.sqlite").exists()
    assert [message.agent for message in result.transcript] == [
        AgentRole.PRODUCT_MANAGER
    ]
    assert result.transcript[0].content.startswith("PM_AGENT_OK")
    assert "onboarding" in result.transcript[0].content.lower()


@pytest.mark.asyncio
async def test_orchestrator_keeps_handoffs_out_of_the_public_transcript(
    tmp_path: Path,
) -> None:
    handlers: dict[AgentRole, AgentHandler] = {
        AgentRole.PRODUCT_MANAGER: _pm_with_handoff,
        AgentRole.MARKET_ANALYST: _market_placeholder,
    }
    request = DispatchRequest(
        message=IncomingDiscordMessage(
            discord_message_id=11,
            discord_server_id="discord-server-456",
            channel_id=21,
            thread_id="discord-thread-456",
            author_id=31,
            content="Help me plan this vertical product and hand off market sizing if needed.",
            directly_mentions_bot=True,
            is_reply_to_bot=False,
        ),
        target_agent=AgentRole.PRODUCT_MANAGER,
        reason="direct_bot_mention",
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
    request = DispatchRequest(
        message=IncomingDiscordMessage(
            discord_message_id=12,
            discord_server_id="discord-server-789",
            channel_id=22,
            thread_id="discord-thread-789",
            author_id=31,
            content="Can you use our connected tools?",
            directly_mentions_bot=True,
            is_reply_to_bot=False,
        ),
        target_agent=AgentRole.PRODUCT_MANAGER,
        reason="direct_bot_mention",
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


@pytest.mark.asyncio
async def test_orchestrator_emits_progress_updates_for_tool_init_and_handoffs(
    tmp_path: Path,
) -> None:
    request = DispatchRequest(
        message=IncomingDiscordMessage(
            discord_message_id=13,
            discord_server_id="discord-server-999",
            channel_id=23,
            thread_id="discord-thread-999",
            author_id=32,
            content="Can you size this opportunity and route the work?",
            directly_mentions_bot=True,
            is_reply_to_bot=False,
        ),
        target_agent=AgentRole.PRODUCT_MANAGER,
        reason="direct_bot_mention",
    )
    initializer = _StaticToolsetInitializer(AgentToolset())
    progress_updates: list[str] = []

    async with PixieOrchestrator(
        checkpoint_path=tmp_path / "progress.sqlite",
        agent_handlers={
            AgentRole.PRODUCT_MANAGER: _pm_with_handoff,
            AgentRole.MARKET_ANALYST: _market_placeholder,
        },
        toolset_initializer=initializer,
    ) as orchestrator:
        await orchestrator.dispatch(
            request,
            status_emitter=progress_updates.append,
        )

    assert progress_updates == [
        "Checking connected tools...",
        "Analyzing with product manager...",
        "Handing off to market analyst...",
        "Analyzing with market analyst...",
    ]


@pytest.mark.asyncio
async def test_orchestrator_emits_internal_product_manager_status_updates(
    tmp_path: Path,
) -> None:
    request = DispatchRequest(
        message=IncomingDiscordMessage(
            discord_message_id=14,
            discord_server_id="discord-server-1000",
            channel_id=24,
            thread_id="discord-thread-1000",
            author_id=33,
            content="Can you assess this product opportunity?",
            directly_mentions_bot=True,
            is_reply_to_bot=False,
        ),
        target_agent=AgentRole.PRODUCT_MANAGER,
        reason="direct_bot_mention",
    )
    progress_updates: list[str] = []

    async with PixieOrchestrator(
        checkpoint_path=tmp_path / "agent-progress.sqlite",
        agent_handlers={
            AgentRole.PRODUCT_MANAGER: build_product_manager_handler(
                model=_ToolCallingFakeListChatModel(
                    responses=[
                        "PM_AGENT_OK Opportunity assessment: retention risk is "
                        "low and GTM looks viable."
                    ]
                )
            )
        },
    ) as orchestrator:
        await orchestrator.dispatch(
            request,
            status_emitter=progress_updates.append,
        )

    assert progress_updates == [
        "Checking connected tools...",
        "Analyzing with product manager...",
        "Product manager is reasoning...",
        "Product manager is drafting the response...",
    ]


@pytest.mark.asyncio
async def test_orchestrator_dispatches_market_requests_to_market_analyst(
    tmp_path: Path,
) -> None:
    request = build_dispatch_request(
        IncomingDiscordMessage(
            discord_message_id=15,
            discord_server_id="discord-server-1001",
            channel_id=25,
            thread_id="discord-thread-1001",
            author_id=34,
            content="Can you size the TAM and review the competitive landscape?",
            directly_mentions_bot=True,
            is_reply_to_bot=False,
        )
    )

    async with PixieOrchestrator(
        checkpoint_path=tmp_path / "dispatcher-market.sqlite",
        agent_handlers={AgentRole.MARKET_ANALYST: _market_placeholder},
    ) as orchestrator:
        result = await orchestrator.dispatch(request)

    assert [message.agent for message in result.transcript] == [
        AgentRole.MARKET_ANALYST
    ]


@pytest.mark.asyncio
async def test_orchestrator_dispatches_ambiguous_requests_to_product_manager(
    tmp_path: Path,
) -> None:
    request = build_dispatch_request(
        IncomingDiscordMessage(
            discord_message_id=16,
            discord_server_id="discord-server-1002",
            channel_id=26,
            thread_id="discord-thread-1002",
            author_id=35,
            content="What should we do next?",
            directly_mentions_bot=True,
            is_reply_to_bot=False,
        )
    )

    async with PixieOrchestrator(
        checkpoint_path=tmp_path / "dispatcher-pm.sqlite",
        agent_handlers={AgentRole.PRODUCT_MANAGER: _pm_direct_response},
    ) as orchestrator:
        result = await orchestrator.dispatch(request)

    assert [message.agent for message in result.transcript] == [
        AgentRole.PRODUCT_MANAGER
    ]


@pytest.mark.asyncio
async def test_orchestrator_dispatcher_rejects_irrelevant_requests(
    tmp_path: Path,
) -> None:
    request = build_dispatch_request(
        IncomingDiscordMessage(
            discord_message_id=17,
            discord_server_id="discord-server-1003",
            channel_id=27,
            thread_id="discord-thread-1003",
            author_id=36,
            content="Write me a pancake recipe.",
            directly_mentions_bot=True,
            is_reply_to_bot=False,
        )
    )

    async with PixieOrchestrator(
        checkpoint_path=tmp_path / "dispatcher-reject.sqlite",
    ) as orchestrator:
        result = await orchestrator.dispatch(request)

    assert [message.agent for message in result.transcript] == [AgentRole.DISPATCHER]
    assert "product" in result.transcript[0].content.lower()


@pytest.mark.asyncio
async def test_orchestrator_rejects_handoffs_back_to_dispatcher(
    tmp_path: Path,
) -> None:
    request = DispatchRequest(
        message=IncomingDiscordMessage(
            discord_message_id=18,
            discord_server_id="discord-server-1004",
            channel_id=28,
            thread_id="discord-thread-1004",
            author_id=37,
            content="Plan the next step.",
            directly_mentions_bot=True,
            is_reply_to_bot=False,
        ),
        target_agent=AgentRole.PRODUCT_MANAGER,
        reason="direct_bot_mention",
    )

    async with PixieOrchestrator(
        checkpoint_path=tmp_path / "dispatcher-invalid-handoff.sqlite",
        agent_handlers={AgentRole.PRODUCT_MANAGER: _invalid_dispatcher_handoff},
    ) as orchestrator:
        with pytest.raises(ValueError, match="dispatcher"):
            await orchestrator.dispatch(request)
