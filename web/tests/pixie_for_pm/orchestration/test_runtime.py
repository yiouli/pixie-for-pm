import logging
from pathlib import Path

import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from pixie_for_pm.agents.registry import (
    AgentHandler,
    build_coordinator_handler,
    build_product_designer_handler,
    build_product_manager_handler,
    build_user_researcher_handler,
)
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


class _NotionCreatePagesArgs(BaseModel):
    pages: list[dict[str, object]] = Field()


class _VercelListProjectsArgs(BaseModel):
    team_name: str | None = Field(default=None)


class _VercelCreateDeploymentArgs(BaseModel):
    project_name: str = Field()
    deployment_summary: str = Field()


async def _pm_with_handoff(context: WorkflowContext) -> AgentExecution:
    del context
    return AgentExecution(
        messages=[],
        handoffs=[
            AgentHandoff(
                source_agent=AgentRole.PRODUCT_MANAGER,
                target_agent=AgentRole.COORDINATOR,
                reason="Need a market sizing pass before drafting the PRD.",
            )
        ],
    )


async def _market_placeholder(context: WorkflowContext) -> AgentExecution:
    return AgentExecution(
        messages=[],
        handoffs=[
            AgentHandoff(
                source_agent=AgentRole.MARKET_ANALYST,
                target_agent=AgentRole.COORDINATOR,
                reason=(
                    "Market sizing complete: "
                    f"Placeholder market analysis response for: {context.user_message}"
                ),
            )
        ],
    )


async def _research_placeholder(context: WorkflowContext) -> AgentExecution:
    return AgentExecution(
        messages=[],
        handoffs=[
            AgentHandoff(
                source_agent=AgentRole.USER_RESEARCHER,
                target_agent=AgentRole.COORDINATOR,
                reason=(
                    "Research synthesis complete: "
                    f"Placeholder research synthesis response for: {context.user_message}"
                ),
            )
        ],
    )


async def _pm_direct_response(context: WorkflowContext) -> AgentExecution:
    return AgentExecution(
        messages=[],
        handoffs=[
            AgentHandoff(
                source_agent=AgentRole.PRODUCT_MANAGER,
                target_agent=AgentRole.COORDINATOR,
                reason=f"PM direct response for: {context.user_message}",
            )
        ],
    )


async def _coordinator_market_router(context: WorkflowContext) -> AgentExecution:
    if context.handoff_context is None:
        return AgentExecution(
            messages=[],
            handoffs=[
                AgentHandoff(
                    source_agent=AgentRole.COORDINATOR,
                    target_agent=AgentRole.PRODUCT_MANAGER,
                    reason="Start planning review.",
                )
            ],
        )

    if context.handoff_context == "Need a market sizing pass before drafting the PRD.":
        return AgentExecution(
            messages=[],
            handoffs=[
                AgentHandoff(
                    source_agent=AgentRole.COORDINATOR,
                    target_agent=AgentRole.MARKET_ANALYST,
                    reason="Run the requested market sizing pass.",
                )
            ],
        )

    return AgentExecution(
        messages=[
            AgentMessage(
                agent=AgentRole.COORDINATOR,
                content=context.handoff_context,
            )
        ]
    )


async def _failing_handler(context: WorkflowContext) -> AgentExecution:
    del context
    raise RuntimeError("agent failure")


async def _invalid_specialist_handoff(context: WorkflowContext) -> AgentExecution:
    return AgentExecution(
        messages=[],
        handoffs=[
            AgentHandoff(
                source_agent=AgentRole.PRODUCT_MANAGER,
                target_agent=AgentRole.PRODUCT_DESIGNER,
                reason="Attempting to bypass coordinator review.",
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


def _demo_toolset() -> AgentToolset:
    return AgentToolset(
        integrations=(
            ConnectedIntegration(
                provider_id="notion",
                provider_name="Notion",
                auth_type="oauth2",
                status="active",
                scopes=("read_content", "update_content"),
                tool_names=("notion_search", "notion_update_page"),
            ),
            ConnectedIntegration(
                provider_id="vercel",
                provider_name="Vercel",
                auth_type="oauth2",
                status="active",
                scopes=("projects.write",),
                tool_names=("vercel_list_projects", "vercel_create_deployment"),
            ),
        )
    )


async def _assert_tool_context(context: WorkflowContext) -> AgentExecution:
    assert context.trigger.discord_server_id == "discord-server-789"
    assert context.trigger.discord_user_id == "31"
    assert [
        integration.provider_id for integration in context.toolset.integrations
    ] == ["notion"]
    assert context.toolset.as_langgraph_tools() == context.toolset.tools
    return AgentExecution(
        messages=[],
        handoffs=[
            AgentHandoff(
                source_agent=AgentRole.PRODUCT_MANAGER,
                target_agent=AgentRole.COORDINATOR,
                reason="Tool-aware placeholder response",
            )
        ],
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
    assert [message.agent for message in result.transcript] == [AgentRole.COORDINATOR]
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
        target_agent=AgentRole.COORDINATOR,
        reason="direct_bot_mention",
    )

    async with PixieOrchestrator(
        checkpoint_path=tmp_path / "handoff.sqlite",
        agent_handlers={
            AgentRole.COORDINATOR: _coordinator_market_router,
            **handlers,
        },
    ) as orchestrator:
        result = await orchestrator.dispatch(request)

    assert [message.agent for message in result.transcript] == [AgentRole.COORDINATOR]
    assert all(
        "handoff" not in message.content.lower() for message in result.transcript
    )
    assert "market sizing complete" in result.transcript[0].content.lower()


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
        target_agent=AgentRole.COORDINATOR,
        reason="direct_bot_mention",
    )
    initializer = _StaticToolsetInitializer(AgentToolset())
    progress_updates: list[str] = []

    async with PixieOrchestrator(
        checkpoint_path=tmp_path / "progress.sqlite",
        agent_handlers={
            AgentRole.COORDINATOR: _coordinator_market_router,
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
        "Analyzing with coordinator...",
        "Handing off to product manager...",
        "Analyzing with product manager...",
        "Handing off to coordinator...",
        "Analyzing with coordinator...",
        "Handing off to market analyst...",
        "Analyzing with market analyst...",
        "Handing off to coordinator...",
        "Analyzing with coordinator...",
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
        "Handing off to coordinator...",
        "Analyzing with coordinator...",
    ]


@pytest.mark.asyncio
async def test_orchestrator_logs_dispatch_failures(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    request = DispatchRequest(
        message=IncomingDiscordMessage(
            discord_message_id=140,
            discord_server_id="discord-server-140",
            channel_id=240,
            thread_id="discord-thread-140",
            author_id=340,
            content="Please investigate this failed Notion update.",
            directly_mentions_bot=True,
            is_reply_to_bot=False,
        ),
        target_agent=AgentRole.USER_RESEARCHER,
        reason="direct_bot_mention",
    )
    caplog.set_level(logging.ERROR, logger="pixie_for_pm.orchestration.runtime")

    async with PixieOrchestrator(
        checkpoint_path=tmp_path / "dispatch-failure.sqlite",
        agent_handlers={AgentRole.USER_RESEARCHER: _failing_handler},
        toolset_initializer=_StaticToolsetInitializer(AgentToolset()),
    ) as orchestrator:
        with pytest.raises(RuntimeError, match="agent failure"):
            await orchestrator.dispatch(request)

    assert "Orchestration dispatch failed" in caplog.text
    assert "target_agent=user_researcher" in caplog.text
    assert "thread_key=discord-thread-140" in caplog.text
    assert "discord_server_id=discord-server-140" in caplog.text


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

    assert [message.agent for message in result.transcript] == [AgentRole.COORDINATOR]
    assert "market analysis response" in result.transcript[0].content.lower()


@pytest.mark.asyncio
async def test_orchestrator_dispatches_research_requests_to_user_researcher(
    tmp_path: Path,
) -> None:
    request = build_dispatch_request(
        IncomingDiscordMessage(
            discord_message_id=151,
            discord_server_id="discord-server-10015",
            channel_id=251,
            thread_id="discord-thread-10015",
            author_id=341,
            content="Synthesize the customer interviews and update our JTBD themes.",
            directly_mentions_bot=True,
            is_reply_to_bot=False,
        )
    )

    async with PixieOrchestrator(
        checkpoint_path=tmp_path / "dispatcher-research.sqlite",
        agent_handlers={AgentRole.USER_RESEARCHER: _research_placeholder},
    ) as orchestrator:
        result = await orchestrator.dispatch(request)

    assert [message.agent for message in result.transcript] == [AgentRole.COORDINATOR]
    assert "research synthesis response" in result.transcript[0].content.lower()


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

    assert [message.agent for message in result.transcript] == [AgentRole.COORDINATOR]
    assert "pm direct response" in result.transcript[0].content.lower()


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

    assert [message.agent for message in result.transcript] == [AgentRole.COORDINATOR]
    assert "product" in result.transcript[0].content.lower()


@pytest.mark.asyncio
async def test_orchestrator_rejects_specialist_handoffs_to_other_specialists(
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
        checkpoint_path=tmp_path / "coordinator-invalid-handoff.sqlite",
        agent_handlers={AgentRole.PRODUCT_MANAGER: _invalid_specialist_handoff},
    ) as orchestrator:
        with pytest.raises(ValueError, match="coordinator"):
            await orchestrator.dispatch(request)


@pytest.mark.asyncio
async def test_orchestrator_runs_retention_demo_discovery_and_deep_dive_flow(
    tmp_path: Path,
) -> None:
    thread_id = "discord-thread-demo"
    tool_calls: list[dict[str, str]] = []

    async def _notion_create_pages(pages: list[dict[str, object]]) -> str:
        assert pages[0]["properties"]["title"] == "Retention Demo PRD - Option #2"
        return (
            '{"results":[{"id":"34f9952098ec810199ddd02c431566ed",'
            '"url":"34f9952098ec810199ddd02c431566ed","type":"page"}]}'
        )

    async def _vercel_create_deployment(
        project_name: str,
        deployment_summary: str,
    ) -> str:
        tool_calls.append(
            {
                "project_name": project_name,
                "deployment_summary": deployment_summary,
            }
        )
        assert project_name == "pixie-retention-demo-discord-thread-demo"
        assert "new next.js project" in deployment_summary.lower()
        return "https://pixie-retention-demo-eval.vercel.app"

    initializer = _StaticToolsetInitializer(
        AgentToolset(
            tools=(
                StructuredTool.from_function(
                    coroutine=_notion_create_pages,
                    name="notion_notion-create-pages",
                    description="Create Notion pages.",
                    args_schema=_NotionCreatePagesArgs,
                ),
                StructuredTool.from_function(
                    coroutine=_vercel_create_deployment,
                    name="vercel_create_deployment",
                    description="Create a Vercel deployment.",
                    args_schema=_VercelCreateDeploymentArgs,
                ),
            ),
            integrations=(
                ConnectedIntegration(
                    provider_id="notion",
                    provider_name="Notion",
                    auth_type="oauth2",
                    status="active",
                    scopes=("write_content",),
                    tool_names=("notion_notion-create-pages",),
                ),
                ConnectedIntegration(
                    provider_id="vercel",
                    provider_name="Vercel",
                    auth_type="oauth2",
                    status="active",
                    scopes=("projects.read", "deployments.write"),
                    tool_names=("vercel_create_deployment",),
                ),
            ),
        )
    )

    async with PixieOrchestrator(
        checkpoint_path=tmp_path / "retention-demo.sqlite",
        agent_handlers={
            AgentRole.COORDINATOR: build_coordinator_handler(
                model=_ToolCallingFakeListChatModel(
                    responses=[
                        (
                            "I’ll review the user interviews first, then I’ll come "
                            "back with the strongest next-build options."
                        ),
                        (
                            "1. Growth follow-up nudges in 1:1 prep\n"
                            "2. Per-report career conversation brief\n"
                            "3. Evidence-linked growth framework\n\n"
                            "If one looks promising, tell me which option you want me "
                            "to turn into a PRD. I also saved the full user interview "
                            "synthesis here: https://www.notion.so/user-interview-synthesis"
                        ),
                        "I’m drafting the PRD for option #2 now.",
                        (
                            "The PRD for option #2 is ready here: "
                            "https://www.notion.so/34f9952098ec810199ddd02c431566ed\n"
                            "Want me to turn that into a quick clickable prototype next?"
                        ),
                        "I’m turning it into a quick clickable prototype now.",
                        (
                            "The prototype is live at "
                            "https://pixie-retention-demo-eval.vercel.app. It focuses "
                            "on the weekly habit loop and follow-through flow. Let me "
                            "know what you want changed."
                        ),
                    ]
                )
            ),
            AgentRole.PRODUCT_MANAGER: build_product_manager_handler(
                model=_ToolCallingFakeListChatModel(
                    responses=[
                        "1. Growth follow-up nudges in 1:1 prep - Idea: surface a "
                        "specific pre-1:1 nudge when a growth thread is unresolved. "
                        "Why: this lands at the moment a manager can act. Proposal: "
                        "detect open growth topics and suggest one follow-up question.\n"
                        "2. Per-report career conversation brief - Idea: generate a "
                        "concise brief for one report. Why: it reduces prep friction. "
                        "Proposal: summarize themes, evidence, and one next step.\n"
                        "3. Evidence-linked growth framework - Idea: connect coaching "
                        "frameworks to note evidence. Why: evidence-backed guidance is "
                        "more credible. Proposal: organize note evidence into growth "
                        "dimensions and highlight gaps.",
                        "Problem statement\nUsers do not build a repeat weekly habit.\n\n"
                        "Goals and non-goals\nIncrease weekly repeat usage without "
                        "adding noisy reminders.",
                        "I drafted the PRD for option #2, handed it to design, and "
                        "the designer prepared a clickable Vercel prototype focused on "
                        "the weekly habit loop. Review the prototype flow and tell me "
                        "what you want changed before we move into delivery.",
                    ]
                )
            ),
            AgentRole.USER_RESEARCHER: build_user_researcher_handler(
                model=_ToolCallingFakeListChatModel(
                    responses=[
                        "Research synthesis: users understand the core value after the "
                        "first session, but they lack a clear reason to come back in "
                        "week two without a guided recurring loop. Notion synthesis "
                        "URL: https://www.notion.so/user-interview-synthesis"
                    ]
                )
            ),
            AgentRole.PRODUCT_DESIGNER: build_product_designer_handler(
                model=_ToolCallingFakeListChatModel(
                    responses=[
                        "Prototype summary: published a clickable Vercel concept for a "
                        "weekly habit loop with a progress rail, next-step CTA, and "
                        "team checkpoint screen."
                    ]
                )
            ),
        },
        toolset_initializer=initializer,
    ) as orchestrator:
        first_result = await orchestrator.dispatch(
            build_dispatch_request(
                IncomingDiscordMessage(
                    discord_message_id=19,
                    discord_server_id="discord-server-demo",
                    channel_id=29,
                    thread_id=thread_id,
                    author_id=38,
                    content=(
                        "It seems that feature X retention is low. What should we "
                        "build next to improve that?"
                    ),
                    directly_mentions_bot=True,
                    is_reply_to_bot=False,
                )
            )
        )
        second_result = await orchestrator.dispatch(
            build_dispatch_request(
                IncomingDiscordMessage(
                    discord_message_id=20,
                    discord_server_id="discord-server-demo",
                    channel_id=29,
                    thread_id=thread_id,
                    author_id=38,
                    content="Go deeper on option #2.",
                    directly_mentions_bot=False,
                    is_reply_to_bot=True,
                )
            )
        )
        third_result = await orchestrator.dispatch(
            build_dispatch_request(
                IncomingDiscordMessage(
                    discord_message_id=21,
                    discord_server_id="discord-server-demo",
                    channel_id=29,
                    thread_id=thread_id,
                    author_id=38,
                    content="sure",
                    directly_mentions_bot=False,
                    is_reply_to_bot=True,
                )
            )
        )

    assert [message.agent for message in first_result.transcript] == [
        AgentRole.COORDINATOR,
        AgentRole.COORDINATOR,
    ]
    assert "user interviews" in first_result.transcript[0].content.lower()
    assert first_result.transcript[-1].content == (
        "1. Growth follow-up nudges in 1:1 prep\n"
        "2. Per-report career conversation brief\n"
        "3. Evidence-linked growth framework\n\n"
        "If one looks promising, tell me which option you want me to turn into a PRD. "
        "I also saved the full user interview synthesis here: "
        "https://www.notion.so/user-interview-synthesis"
    )

    assert [message.agent for message in second_result.transcript] == [
        AgentRole.COORDINATOR,
        AgentRole.COORDINATOR,
    ]
    assert "drafting the prd" in second_result.transcript[0].content.lower()
    second_turn_content = second_result.transcript[-1].content
    assert "PRD for option #2" in second_turn_content
    assert (
        "https://www.notion.so/34f9952098ec810199ddd02c431566ed" in second_turn_content
    )
    assert "prototype" in second_turn_content.lower()

    assert [message.agent for message in third_result.transcript] == [
        AgentRole.COORDINATOR,
        AgentRole.COORDINATOR,
    ]
    assert "clickable prototype" in third_result.transcript[0].content.lower()
    third_turn_content = third_result.transcript[-1].content
    assert "prototype" in third_turn_content.lower()
    assert "https://pixie-retention-demo-eval.vercel.app" in third_turn_content
    assert "let me know what you want changed" in third_turn_content.lower()
    assert tool_calls == [
        {
            "project_name": "pixie-retention-demo-discord-thread-demo",
            "deployment_summary": (
                "Create a new Next.js project named "
                "pixie-retention-demo-discord-thread-demo for this clickable "
                "prototype. Prototype summary: published a clickable Vercel concept "
                "for a weekly habit loop with a progress rail, next-step CTA, and "
                "team checkpoint screen."
            ),
        }
    ]


@pytest.mark.asyncio
async def test_orchestrator_retention_demo_does_not_stream_specialist_drafts(
    tmp_path: Path,
) -> None:
    thread_id = "discord-thread-demo"
    streamed_chunks: list[str] = []

    async def _notion_create_pages(pages: list[dict[str, object]]) -> str:
        del pages
        return "https://www.notion.so/user-interview-synthesis"

    initializer = _StaticToolsetInitializer(
        AgentToolset(
            tools=(
                StructuredTool.from_function(
                    coroutine=_notion_create_pages,
                    name="notion_notion-create-pages",
                    description="Create Notion pages.",
                    args_schema=_NotionCreatePagesArgs,
                ),
            ),
            integrations=(
                ConnectedIntegration(
                    provider_id="notion",
                    provider_name="Notion",
                    auth_type="oauth2",
                    status="active",
                    scopes=("write_content",),
                    tool_names=("notion_notion-create-pages",),
                ),
            ),
        )
    )

    async with PixieOrchestrator(
        checkpoint_path=tmp_path / "retention-demo-streaming.sqlite",
        agent_handlers={
            AgentRole.COORDINATOR: build_coordinator_handler(
                model=_ToolCallingFakeListChatModel(
                    responses=[
                        (
                            "I’ll review the user interviews first, then I’ll come "
                            "back with the strongest next-build options."
                        ),
                        (
                            "1. Growth follow-up nudges in 1:1 prep\n"
                            "2. Per-report career conversation brief\n"
                            "3. Evidence-linked growth framework\n\n"
                            "If one looks promising, tell me which option you want me "
                            "to turn into a PRD. I also saved the full user interview "
                            "synthesis here: https://www.notion.so/user-interview-synthesis"
                        ),
                    ]
                )
            ),
            AgentRole.PRODUCT_MANAGER: build_product_manager_handler(
                model=_ToolCallingFakeListChatModel(
                    responses=[
                        "1. Growth follow-up nudges in 1:1 prep - Idea: surface a "
                        "specific pre-1:1 nudge when a growth thread is unresolved. "
                        "Why: this lands at the moment a manager can act. Proposal: "
                        "detect open growth topics and suggest one follow-up question.\n"
                        "2. Per-report career conversation brief - Idea: generate a "
                        "concise brief for one report. Why: it reduces prep friction. "
                        "Proposal: summarize themes, evidence, and one next step.\n"
                        "3. Evidence-linked growth framework - Idea: connect coaching "
                        "frameworks to note evidence. Why: evidence-backed guidance is "
                        "more credible. Proposal: organize note evidence into growth "
                        "dimensions and highlight gaps."
                    ]
                )
            ),
            AgentRole.USER_RESEARCHER: build_user_researcher_handler(
                model=_ToolCallingFakeListChatModel(
                    responses=[
                        "Research synthesis: users understand the core value after the "
                        "first session, but they lack a clear reason to come back in "
                        "week two without a guided recurring loop. Notion synthesis "
                        "URL: https://www.notion.so/user-interview-synthesis"
                    ]
                )
            ),
        },
        toolset_initializer=initializer,
    ) as orchestrator:
        result = await orchestrator.dispatch(
            build_dispatch_request(
                IncomingDiscordMessage(
                    discord_message_id=19,
                    discord_server_id="discord-server-demo",
                    channel_id=29,
                    thread_id=thread_id,
                    author_id=38,
                    content=(
                        "It seems that feature X retention is low. What should we "
                        "build next to improve that?"
                    ),
                    directly_mentions_bot=True,
                    is_reply_to_bot=False,
                )
            ),
            response_emitter=streamed_chunks.append,
        )

    assert [message.agent for message in result.transcript] == [
        AgentRole.COORDINATOR,
        AgentRole.COORDINATOR,
    ]
    streamed_text = "".join(streamed_chunks)
    assert "idea:" not in streamed_text.lower()
    assert "proposal:" not in streamed_text.lower()
    assert "which option you want me to turn into a prd" in streamed_text.lower()
