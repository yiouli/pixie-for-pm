import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel

from pixie_for_pm.agents.registry import (
    build_dispatcher_handler,
    build_product_manager_handler,
    build_user_researcher_handler,
    default_agent_handlers,
)
from pixie_for_pm.domain.models import AgentRole, WorkflowContext
from pixie_for_pm.integrations.toolset import (
    AgentToolset,
    ConnectedIntegration,
    DiscordTriggerContext,
)


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


@pytest.mark.asyncio
async def test_dispatcher_handler_routes_market_requests_to_market_analyst() -> None:
    handler = build_dispatcher_handler()

    execution = await handler(
        WorkflowContext(
            thread_key="discord-thread-1",
            current_agent=AgentRole.DISPATCHER,
            user_message="Can you size the TAM and review the competitive landscape?",
            transcript=(),
            trigger=DiscordTriggerContext(
                discord_server_id="discord-server-1",
                discord_user_id="user-1",
                channel_id=10,
                thread_id="discord-thread-1",
                message_id=99,
                thread_key="discord-thread-1",
                dispatch_reason="direct_bot_mention",
            ),
            toolset=AgentToolset(),
        )
    )

    assert execution.messages == []
    assert [handoff.target_agent for handoff in execution.handoffs] == [
        AgentRole.MARKET_ANALYST
    ]


@pytest.mark.asyncio
async def test_dispatcher_handler_routes_research_requests_to_user_researcher() -> None:
    handler = build_dispatcher_handler()

    execution = await handler(
        WorkflowContext(
            thread_key="discord-thread-1",
            current_agent=AgentRole.DISPATCHER,
            user_message=(
                "Synthesize the last five customer interviews and update our JTBD "
                "research themes."
            ),
            transcript=(),
            trigger=DiscordTriggerContext(
                discord_server_id="discord-server-1",
                discord_user_id="user-1",
                channel_id=10,
                thread_id="discord-thread-1",
                message_id=99,
                thread_key="discord-thread-1",
                dispatch_reason="direct_bot_mention",
            ),
            toolset=AgentToolset(),
        )
    )

    assert execution.messages == []
    assert [handoff.target_agent for handoff in execution.handoffs] == [
        AgentRole.USER_RESEARCHER
    ]


@pytest.mark.asyncio
async def test_dispatcher_handler_falls_back_to_product_manager_for_ambiguous_requests() -> (
    None
):
    handler = build_dispatcher_handler()

    execution = await handler(
        WorkflowContext(
            thread_key="discord-thread-1",
            current_agent=AgentRole.DISPATCHER,
            user_message="What should we do next?",
            transcript=(),
            trigger=DiscordTriggerContext(
                discord_server_id="discord-server-1",
                discord_user_id="user-1",
                channel_id=10,
                thread_id="discord-thread-1",
                message_id=99,
                thread_key="discord-thread-1",
                dispatch_reason="direct_bot_mention",
            ),
            toolset=AgentToolset(),
        )
    )

    assert execution.messages == []
    assert [handoff.target_agent for handoff in execution.handoffs] == [
        AgentRole.PRODUCT_MANAGER
    ]


@pytest.mark.asyncio
async def test_dispatcher_handler_rejects_irrelevant_requests_directly() -> None:
    handler = build_dispatcher_handler()

    execution = await handler(
        WorkflowContext(
            thread_key="discord-thread-1",
            current_agent=AgentRole.DISPATCHER,
            user_message="Write me a pancake recipe.",
            transcript=(),
            trigger=DiscordTriggerContext(
                discord_server_id="discord-server-1",
                discord_user_id="user-1",
                channel_id=10,
                thread_id="discord-thread-1",
                message_id=99,
                thread_key="discord-thread-1",
                dispatch_reason="direct_bot_mention",
            ),
            toolset=AgentToolset(),
        )
    )

    assert execution.handoffs == []
    assert execution.messages[0].agent is AgentRole.DISPATCHER
    assert "product" in execution.messages[0].content.lower()


@pytest.mark.asyncio
async def test_product_manager_handler_returns_deep_agent_response() -> None:
    handler = build_product_manager_handler(
        model=_ToolCallingFakeListChatModel(
            responses=[
                "PM_AGENT_OK Product brief ready: focus on activation, retention, "
                "and analytics instrumentation."
            ]
        )
    )

    execution = await handler(
        WorkflowContext(
            thread_key="discord-thread-1",
            current_agent=AgentRole.PRODUCT_MANAGER,
            user_message="Can you help me test the Discord bot?",
            transcript=(),
            trigger=DiscordTriggerContext(
                discord_server_id="discord-server-1",
                discord_user_id="user-1",
                channel_id=10,
                thread_id="discord-thread-1",
                message_id=99,
                thread_key="discord-thread-1",
                dispatch_reason="direct_bot_mention",
            ),
            toolset=AgentToolset(),
        )
    )

    assert execution.handoffs == []
    assert execution.messages[0].agent is AgentRole.PRODUCT_MANAGER
    assert execution.messages[0].content.startswith("PM_AGENT_OK")
    assert "activation" in execution.messages[0].content.lower()


@pytest.mark.asyncio
async def test_product_manager_handler_emits_streamed_content_deltas() -> None:
    streamed_chunks: list[str] = []
    handler = build_product_manager_handler(
        model=_ToolCallingFakeListChatModel(
            responses=["PM_AGENT_OK Live streamed response for Discord delivery."]
        )
    )

    execution = await handler(
        WorkflowContext(
            thread_key="discord-thread-1",
            current_agent=AgentRole.PRODUCT_MANAGER,
            user_message="Can you help me test streamed Discord output?",
            transcript=(),
            trigger=DiscordTriggerContext(
                discord_server_id="discord-server-1",
                discord_user_id="user-1",
                channel_id=10,
                thread_id="discord-thread-1",
                message_id=99,
                thread_key="discord-thread-1",
                dispatch_reason="direct_bot_mention",
            ),
            toolset=AgentToolset(),
            response_emitter=streamed_chunks.append,
        )
    )

    assert "".join(streamed_chunks) == execution.messages[0].content
    assert streamed_chunks != []


@pytest.mark.asyncio
async def test_user_researcher_handler_requires_notion_connection() -> None:
    handler = build_user_researcher_handler(
        model=_ToolCallingFakeListChatModel(
            responses=["This response should not be used without Notion."]
        )
    )

    execution = await handler(
        WorkflowContext(
            thread_key="discord-thread-1",
            current_agent=AgentRole.USER_RESEARCHER,
            user_message="Synthesize these interviews into themes.",
            transcript=(),
            trigger=DiscordTriggerContext(
                discord_server_id="discord-server-1",
                discord_user_id="user-1",
                channel_id=10,
                thread_id="discord-thread-1",
                message_id=99,
                thread_key="discord-thread-1",
                dispatch_reason="direct_bot_mention",
            ),
            toolset=AgentToolset(),
        )
    )

    assert execution.handoffs == []
    assert execution.messages[0].agent is AgentRole.USER_RESEARCHER
    assert "notion" in execution.messages[0].content.lower()
    assert "connect" in execution.messages[0].content.lower()


@pytest.mark.asyncio
async def test_user_researcher_handler_returns_deep_agent_response() -> None:
    handler = build_user_researcher_handler(
        model=_ToolCallingFakeListChatModel(
            responses=[
                "USER_RESEARCH_AGENT_OK Themes updated in Notion: onboarding friction, "
                "manual synthesis overhead, and unclear JTBD language."
            ]
        )
    )

    execution = await handler(
        WorkflowContext(
            thread_key="discord-thread-1",
            current_agent=AgentRole.USER_RESEARCHER,
            user_message="Read the interview transcripts and produce a synthesis.",
            transcript=(),
            trigger=DiscordTriggerContext(
                discord_server_id="discord-server-1",
                discord_user_id="user-1",
                channel_id=10,
                thread_id="discord-thread-1",
                message_id=99,
                thread_key="discord-thread-1",
                dispatch_reason="direct_bot_mention",
            ),
            toolset=AgentToolset(
                integrations=(
                    ConnectedIntegration(
                        provider_id="notion",
                        provider_name="Notion",
                        auth_type="oauth2",
                        status="active",
                        scopes=("read_content", "update_content"),
                        tool_names=("notion_search", "notion_update_page"),
                    ),
                )
            ),
        )
    )

    assert execution.handoffs == []
    assert execution.messages[0].agent is AgentRole.USER_RESEARCHER
    assert execution.messages[0].content.startswith("USER_RESEARCH_AGENT_OK")
    assert "notion" in execution.messages[0].content.lower()


@pytest.mark.asyncio
async def test_default_handlers_keep_placeholder_contract_for_unimplemented_roles() -> (
    None
):
    handler = default_agent_handlers()[AgentRole.MARKET_ANALYST]

    execution = await handler(
        WorkflowContext(
            thread_key="discord-thread-1",
            current_agent=AgentRole.MARKET_ANALYST,
            user_message="Can you help me test the Discord bot?",
            transcript=(),
            trigger=DiscordTriggerContext(
                discord_server_id="discord-server-1",
                discord_user_id="user-1",
                channel_id=10,
                thread_id="discord-thread-1",
                message_id=99,
                thread_key="discord-thread-1",
                dispatch_reason="direct_bot_mention",
            ),
            toolset=AgentToolset(),
        )
    )

    assert execution.messages[0].content.startswith("E2E_PLACEHOLDER_OK")
    assert "market analyst" in execution.messages[0].content.lower()


def test_default_handlers_include_user_researcher() -> None:
    assert AgentRole.USER_RESEARCHER in default_agent_handlers()


def test_default_handlers_include_dispatcher() -> None:
    assert AgentRole.DISPATCHER in default_agent_handlers()
