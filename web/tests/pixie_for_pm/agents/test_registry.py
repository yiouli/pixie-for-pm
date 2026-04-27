import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from pixie_for_pm.agents.demo_flow import (
    BLOCKED_STATUS,
    OPTIONS_SUMMARY_STAGE,
    PRD_BRIEF_STAGE,
    PRD_READY_STAGE,
    PROTOTYPE_BRIEF_STAGE,
    PROTOTYPE_SUMMARY_STAGE,
    RESEARCH_BRIEF_STAGE,
    RESEARCH_FINDINGS_STAGE,
    parse_demo_handoff,
    serialize_demo_handoff,
)
from pixie_for_pm.agents.product_manager import PRODUCT_MANAGER_SYSTEM_PROMPT
from pixie_for_pm.agents.registry import (
    build_dispatcher_handler,
    build_product_designer_handler,
    build_product_manager_handler,
    build_user_researcher_handler,
    default_agent_handlers,
)
from pixie_for_pm.agents.user_researcher import _build_execution_context
from pixie_for_pm.domain.models import AgentMessage, AgentRole, WorkflowContext
from pixie_for_pm.integrations.toolset import (
    AgentToolset,
    ConnectedIntegration,
    DiscordTriggerContext,
    IntegrationLoadFailure,
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


class _NotionUpdateArgs(BaseModel):
    page_title: str = Field()
    content_updates: str = Field()


class _NotionCreatePagesArgs(BaseModel):
    pages: list[dict[str, object]] = Field()


class _VercelListProjectsArgs(BaseModel):
    team_name: str | None = Field(default=None)


class _VercelCreateDeploymentArgs(BaseModel):
    project_name: str = Field()
    deployment_summary: str = Field()


class _VercelDeployToVercelArgs(BaseModel):
    project_name: str | None = Field(default=None)
    deployment_summary: str | None = Field(default=None)


def test_user_researcher_execution_context_requires_search_before_fetch() -> None:
    context = _build_execution_context(
        WorkflowContext(
            thread_key="discord-thread-context",
            current_agent=AgentRole.USER_RESEARCHER,
            user_message="Synthesize the research.",
            transcript=(),
            trigger=DiscordTriggerContext(
                discord_server_id="discord-server-context",
                discord_user_id="user-context",
                channel_id=10,
                thread_id="discord-thread-context",
                message_id=99,
                thread_key="discord-thread-context",
                dispatch_reason="direct_bot_mention",
            ),
            toolset=AgentToolset(
                integrations=(
                    ConnectedIntegration(
                        provider_id="notion",
                        provider_name="Notion",
                        auth_type="oauth2",
                        status="active",
                        scopes=("read_content",),
                        tool_names=("notion_notion-search", "notion_notion-fetch"),
                    ),
                )
            ),
        )
    )

    assert "search notion first" in context.lower()
    assert "do not invent notion:// locators" in context.lower()
    assert "notion_notion-fetch" in context


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
async def test_dispatcher_handler_routes_retention_strategy_questions_to_product_manager() -> (
    None
):
    handler = build_dispatcher_handler()

    execution = await handler(
        WorkflowContext(
            thread_key="discord-thread-1",
            current_agent=AgentRole.DISPATCHER,
            user_message=(
                "It seems that feature X retention is low. What should we build "
                "next to improve that?"
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

    assert [message.agent for message in execution.messages] == [AgentRole.COORDINATOR]
    assert "user interviews" in execution.messages[0].content.lower()
    assert [handoff.target_agent for handoff in execution.handoffs] == [
        AgentRole.USER_RESEARCHER
    ]
    demo_payload = parse_demo_handoff(execution.handoffs[0].reason)
    assert demo_payload is not None
    assert demo_payload.stage == RESEARCH_BRIEF_STAGE


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
    assert execution.messages[0].agent is AgentRole.COORDINATOR
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

    assert execution.messages == []
    assert [handoff.target_agent for handoff in execution.handoffs] == [
        AgentRole.COORDINATOR
    ]
    assert execution.handoffs[0].reason.startswith("PM_AGENT_OK")
    assert "activation" in execution.handoffs[0].reason.lower()


@pytest.mark.asyncio
async def test_product_manager_handler_turns_research_findings_into_coordinator_handoff() -> (
    None
):
    handler = build_product_manager_handler(
        model=_ToolCallingFakeListChatModel(
            responses=[
                (
                    "1. Guided loop - Idea: Add a weekly prep loop. "
                    "Why: It creates a repeat habit. Proposal: Show the next "
                    "step before each 1:1.\n"
                    "2. Manager brief - Idea: Generate a career brief. "
                    "Why: It reduces prep friction. Proposal: Auto-build a concise "
                    "report.\n"
                    "3. Evidence link - Idea: Connect growth frameworks to evidence. "
                    "Why: It boosts confidence. Proposal: Attach supporting signals."
                )
            ]
        )
    )

    execution = await handler(
        WorkflowContext(
            thread_key="discord-thread-1",
            current_agent=AgentRole.PRODUCT_MANAGER,
            user_message="unused for handoff-driven demo stage",
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
            handoff_context=serialize_demo_handoff(
                stage=RESEARCH_FINDINGS_STAGE,
                artifact="ignored",
            ),
        )
    )

    assert execution.messages == []
    assert [handoff.target_agent for handoff in execution.handoffs] == [
        AgentRole.COORDINATOR
    ]
    demo_payload = parse_demo_handoff(execution.handoffs[0].reason)
    assert demo_payload is not None
    assert demo_payload.stage == OPTIONS_SUMMARY_STAGE
    assert demo_payload.artifact.startswith("1.")


@pytest.mark.asyncio
async def test_product_manager_retention_handoff_does_not_publish_directly() -> None:
    handler = build_product_manager_handler(
        model=_ToolCallingFakeListChatModel(responses=["unused"])
    )
    public_messages: list[str] = []

    execution = await handler(
        WorkflowContext(
            thread_key="discord-thread-1",
            current_agent=AgentRole.PRODUCT_MANAGER,
            user_message=(
                "It seems that feature X retention is low. What should we build "
                "next to improve that?"
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
            public_message_emitter=public_messages.append,
        )
    )

    assert execution.messages == []
    assert [handoff.target_agent for handoff in execution.handoffs] == [
        AgentRole.COORDINATOR
    ]
    assert public_messages == []


@pytest.mark.asyncio
async def test_product_manager_handler_asks_for_prototype_approval_after_deep_dive() -> (
    None
):
    handler = build_product_manager_handler(
        model=_ToolCallingFakeListChatModel(
            responses=[
                "Problem\nFeature X retention is weak after week two.\n\nGoals\n"
                "Increase repeat usage."
            ]
        )
    )

    execution = await handler(
        WorkflowContext(
            thread_key="discord-thread-1",
            current_agent=AgentRole.PRODUCT_MANAGER,
            user_message="Draft the PRD for the selected option.",
            transcript=(),
            trigger=DiscordTriggerContext(
                discord_server_id="discord-server-1",
                discord_user_id="user-1",
                channel_id=10,
                thread_id="discord-thread-1",
                message_id=99,
                thread_key="discord-thread-1",
                dispatch_reason="reply_to_bot",
            ),
            toolset=AgentToolset(),
            handoff_context=serialize_demo_handoff(
                stage=PRD_BRIEF_STAGE,
                artifact="Selected option: #1\nUser request: Go deeper on option #1.",
            ),
        )
    )

    assert execution.messages == []
    assert [handoff.target_agent for handoff in execution.handoffs] == [
        AgentRole.COORDINATOR
    ]
    demo_payload = parse_demo_handoff(execution.handoffs[0].reason)
    assert demo_payload is not None
    assert demo_payload.stage == PRD_READY_STAGE
    assert "prd for option #1" in demo_payload.artifact.lower()
    assert "prototype" in demo_payload.artifact.lower()


@pytest.mark.asyncio
async def test_product_manager_handler_persists_demo_prd_and_asks_for_prototype() -> (
    None
):
    saved_pages: list[dict[str, str]] = []

    async def _notion_update_content(page_title: str, content_updates: str) -> str:
        saved_pages.append(
            {
                "page_title": page_title,
                "content_updates": content_updates,
            }
        )
        return f"Saved {page_title} at https://www.notion.so/saved-prd-page"

    handler = build_product_manager_handler(
        model=_ToolCallingFakeListChatModel(
            responses=[
                (
                    "Title and one-sentence product thesis\n"
                    "Weekly prep loop improves repeat usage.\n\n"
                    "Problem statement\nManagers lose continuity between 1:1s.\n\n"
                    "Why now\nRetention is weak after the first use.\n\n"
                    "Target user and core job to be done\n"
                    "Managers preparing for weekly 1:1s.\n\n"
                    "Key insights and evidence\nUsers want one concrete next step "
                    "tied to prior evidence.\n\n"
                    "Goals and non-goals\nIncrease repeat weekly usage without "
                    "adding noisy reminders.\n\n"
                    "Hypotheses\nA guided weekly prep loop will improve return usage.\n\n"
                    "Solution overview\nShow one suggested follow-up before each 1:1.\n\n"
                    "MVP scope\nRecap, suggestion, agenda carry-forward.\n\n"
                    "User experience notes\nKeep prep lightweight and contextual.\n\n"
                    "Success metrics\nWeekly repeat usage and follow-up completion.\n\n"
                    "Launch and iteration plan\nPilot with active managers first.\n\n"
                    "Risks and open questions\nNeed to validate if prompts beat summaries."
                )
            ]
        )
    )

    execution = await handler(
        WorkflowContext(
            thread_key="discord-thread-1",
            current_agent=AgentRole.PRODUCT_MANAGER,
            user_message="Draft the PRD for the selected option.",
            transcript=(),
            trigger=DiscordTriggerContext(
                discord_server_id="discord-server-1",
                discord_user_id="user-1",
                channel_id=10,
                thread_id="discord-thread-1",
                message_id=99,
                thread_key="discord-thread-1",
                dispatch_reason="reply_to_bot",
            ),
            toolset=AgentToolset(
                tools=(
                    StructuredTool.from_function(
                        coroutine=_notion_update_content,
                        name="notion_update_content",
                        description="Save PRDs to Notion.",
                        args_schema=_NotionUpdateArgs,
                    ),
                )
            ),
            handoff_context=serialize_demo_handoff(
                stage=PRD_BRIEF_STAGE,
                artifact="Selected option: #2\nUser request: Go deeper on option #2.",
            ),
        )
    )

    assert saved_pages
    assert "prd" in saved_pages[0]["page_title"].lower()
    assert "problem statement" in saved_pages[0]["content_updates"].lower()
    assert execution.messages == []
    assert [handoff.target_agent for handoff in execution.handoffs] == [
        AgentRole.COORDINATOR
    ]
    demo_payload = parse_demo_handoff(execution.handoffs[0].reason)
    assert demo_payload is not None
    assert demo_payload.stage == PRD_READY_STAGE
    assert "https://www.notion.so/saved-prd-page" in demo_payload.artifact
    assert "prototype" in demo_payload.artifact.lower()


@pytest.mark.asyncio
async def test_dispatcher_handler_handoffs_to_designer_on_prototype_approval() -> None:
    handler = build_dispatcher_handler()

    execution = await handler(
        WorkflowContext(
            thread_key="discord-thread-1",
            current_agent=AgentRole.COORDINATOR,
            user_message="sure",
            transcript=(
                AgentMessage(
                    agent=AgentRole.COORDINATOR,
                    content=(
                        "PRD for option #2 ready: https://www.notion.so/prd-option-2\n"
                        "Want me to spin up a quick clickable prototype for it next?"
                    ),
                ),
            ),
            trigger=DiscordTriggerContext(
                discord_server_id="discord-server-1",
                discord_user_id="user-1",
                channel_id=10,
                thread_id="discord-thread-1",
                message_id=100,
                thread_key="discord-thread-1",
                dispatch_reason="reply_to_bot",
            ),
            toolset=AgentToolset(),
        )
    )

    assert [message.agent for message in execution.messages] == [AgentRole.COORDINATOR]
    assert execution.messages[0].content.lower() == "on it."
    assert [handoff.target_agent for handoff in execution.handoffs] == [
        AgentRole.PRODUCT_DESIGNER
    ]
    demo_payload = parse_demo_handoff(execution.handoffs[0].reason)
    assert demo_payload is not None
    assert demo_payload.stage == PROTOTYPE_BRIEF_STAGE
    assert "https://www.notion.so/prd-option-2" in demo_payload.artifact


@pytest.mark.asyncio
async def test_product_manager_handler_handoffs_to_designer_on_prototype_approval() -> (
    None
):
    handler = build_product_manager_handler(
        model=_ToolCallingFakeListChatModel(responses=[""]),
    )

    execution = await handler(
        WorkflowContext(
            thread_key="discord-thread-1",
            current_agent=AgentRole.PRODUCT_MANAGER,
            user_message="sure",
            transcript=(
                AgentMessage(
                    agent=AgentRole.PRODUCT_MANAGER,
                    content=(
                        "PRD for option #2 ready: https://www.notion.so/prd-option-2\n"
                        "Want me to spin up a quick clickable prototype for it next?"
                    ),
                ),
            ),
            trigger=DiscordTriggerContext(
                discord_server_id="discord-server-1",
                discord_user_id="user-1",
                channel_id=10,
                thread_id="discord-thread-1",
                message_id=100,
                thread_key="discord-thread-1",
                dispatch_reason="reply_to_bot",
            ),
            toolset=AgentToolset(),
        )
    )

    assert execution.messages == []
    assert [handoff.target_agent for handoff in execution.handoffs] == [
        AgentRole.COORDINATOR
    ]


@pytest.mark.asyncio
async def test_product_manager_handler_surfaces_notion_url_from_create_page_identifier() -> (
    None
):
    async def _notion_create_pages(pages: list[dict[str, object]]) -> str:
        properties = pages[0].get("properties")
        assert isinstance(properties, dict)
        assert properties.get("title") == "Retention Demo PRD - Option #2"
        return (
            '{"results":[{"id":"34f9952098ec810199ddd02c431566ed",'
            '"url":"34f9952098ec810199ddd02c431566ed","type":"page"}]}'
        )

    handler = build_product_manager_handler(
        model=_ToolCallingFakeListChatModel(
            responses=["Problem statement\nUsers do not build a repeat weekly habit."]
        )
    )

    execution = await handler(
        WorkflowContext(
            thread_key="discord-thread-1",
            current_agent=AgentRole.PRODUCT_MANAGER,
            user_message="Go deeper on option #2.",
            transcript=(),
            trigger=DiscordTriggerContext(
                discord_server_id="discord-server-1",
                discord_user_id="user-1",
                channel_id=10,
                thread_id="discord-thread-1",
                message_id=99,
                thread_key="discord-thread-1",
                dispatch_reason="reply_to_bot",
            ),
            toolset=AgentToolset(
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
            ),
            handoff_context=serialize_demo_handoff(
                stage=PRD_BRIEF_STAGE,
                artifact="Selected option: #2",
            ),
        )
    )

    demo_payload = parse_demo_handoff(execution.handoffs[0].reason)
    assert demo_payload is not None
    assert demo_payload.stage == PRD_READY_STAGE
    assert (
        "https://www.notion.so/34f9952098ec810199ddd02c431566ed"
        in demo_payload.artifact
    )
    assert "spin up a quick clickable prototype" in demo_payload.artifact.lower()


@pytest.mark.asyncio
async def test_product_designer_handler_publishes_demo_prototype_before_pm_handoff() -> (
    None
):
    tool_calls: list[dict[str, str | None]] = []

    async def _vercel_list_projects(team_name: str | None = None) -> str:
        tool_calls.append({"tool": "vercel_list_projects", "team_name": team_name})
        return "pixie-retention-demo"

    async def _vercel_create_deployment(
        project_name: str,
        deployment_summary: str,
    ) -> str:
        tool_calls.append(
            {
                "tool": "vercel_create_deployment",
                "project_name": project_name,
                "deployment_summary": deployment_summary,
            }
        )
        return "https://pixie-retention-demo-eval.vercel.app"

    handler = build_product_designer_handler(
        model=_ToolCallingFakeListChatModel(
            responses=[
                (
                    "Prototype summary: A weekly prep loop surfaces one suggested "
                    "follow-up before each 1:1.\n\n"
                    "Core user journey\n1. Open prep.\n2. Review one suggested "
                    "follow-up.\n3. Carry it into the agenda.\n\n"
                    "Critical screens and states\n"
                    "Prep recap, suggestion card, agenda state.\n\n"
                    "Interaction model\n"
                    "Lightweight, evidence-backed recommendation.\n\n"
                    "Open questions\nHow much evidence detail managers need."
                )
            ]
        )
    )

    execution = await handler(
        WorkflowContext(
            thread_key="discord-thread-1",
            current_agent=AgentRole.PRODUCT_DESIGNER,
            user_message="Go deeper on option #2.",
            transcript=(),
            trigger=DiscordTriggerContext(
                discord_server_id="discord-server-1",
                discord_user_id="user-1",
                channel_id=10,
                thread_id="discord-thread-1",
                message_id=99,
                thread_key="discord-thread-1",
                dispatch_reason="reply_to_bot",
            ),
            toolset=AgentToolset(
                tools=(
                    StructuredTool.from_function(
                        coroutine=_vercel_list_projects,
                        name="vercel_list_projects",
                        description="List Vercel projects.",
                        args_schema=_VercelListProjectsArgs,
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
                        provider_id="vercel",
                        provider_name="Vercel",
                        auth_type="oauth2",
                        status="active",
                        scopes=("projects.read", "deployments.write"),
                        tool_names=("vercel_list_projects", "vercel_create_deployment"),
                    ),
                ),
            ),
            handoff_context=serialize_demo_handoff(
                stage=PROTOTYPE_BRIEF_STAGE,
                artifact="PRD content",
            ),
        )
    )

    assert execution.messages == []
    assert [call["tool"] for call in tool_calls] == [
        "vercel_list_projects",
        "vercel_create_deployment",
    ]
    assert tool_calls[1]["project_name"] == "pixie-retention-demo"
    assert [handoff.target_agent for handoff in execution.handoffs] == [
        AgentRole.COORDINATOR
    ]
    assert (
        "https://pixie-retention-demo-eval.vercel.app" in execution.handoffs[0].reason
    )


@pytest.mark.asyncio
async def test_product_designer_handler_marks_manual_vercel_deploy_as_blocked() -> None:
    tool_calls: list[dict[str, str | None]] = []

    async def _vercel_list_projects(team_name: str | None = None) -> str:
        tool_calls.append({"tool": "vercel_list_projects", "team_name": team_name})
        return "pixie-retention-demo"

    async def _vercel_deploy_to_vercel(
        project_name: str | None = None,
        deployment_summary: str | None = None,
    ) -> str:
        tool_calls.append(
            {
                "tool": "vercel_deploy_to_vercel",
                "project_name": project_name,
                "deployment_summary": deployment_summary,
            }
        )
        return "To deploy this to Vercel, run the Vercel CLI command `vercel deploy`."

    handler = build_product_designer_handler(
        model=_ToolCallingFakeListChatModel(
            responses=[
                (
                    "Prototype summary: A weekly prep loop surfaces one suggested "
                    "follow-up before each 1:1.\n\n"
                    "Core user journey\n1. Open prep.\n2. Review one suggested "
                    "follow-up.\n3. Carry it into the agenda.\n\n"
                    "Critical screens and states\n"
                    "Prep recap, suggestion card, agenda state.\n\n"
                    "Interaction model\n"
                    "Lightweight, evidence-backed recommendation.\n\n"
                    "Open questions\nHow much evidence detail managers need."
                )
            ]
        )
    )

    execution = await handler(
        WorkflowContext(
            thread_key="discord-thread-1",
            current_agent=AgentRole.PRODUCT_DESIGNER,
            user_message="Go deeper on option #2.",
            transcript=(),
            trigger=DiscordTriggerContext(
                discord_server_id="discord-server-1",
                discord_user_id="user-1",
                channel_id=10,
                thread_id="discord-thread-1",
                message_id=99,
                thread_key="discord-thread-1",
                dispatch_reason="reply_to_bot",
            ),
            toolset=AgentToolset(
                tools=(
                    StructuredTool.from_function(
                        coroutine=_vercel_list_projects,
                        name="vercel_list_projects",
                        description="List Vercel projects.",
                        args_schema=_VercelListProjectsArgs,
                    ),
                    StructuredTool.from_function(
                        coroutine=_vercel_deploy_to_vercel,
                        name="vercel_deploy_to_vercel",
                        description="Deploy to Vercel.",
                        args_schema=_VercelDeployToVercelArgs,
                    ),
                ),
                integrations=(
                    ConnectedIntegration(
                        provider_id="vercel",
                        provider_name="Vercel",
                        auth_type="oauth2",
                        status="active",
                        scopes=("projects.read", "deployments.write"),
                        tool_names=("vercel_list_projects", "vercel_deploy_to_vercel"),
                    ),
                ),
            ),
            handoff_context=serialize_demo_handoff(
                stage=PROTOTYPE_BRIEF_STAGE,
                artifact="PRD content",
            ),
        )
    )

    assert [call["tool"] for call in tool_calls] == [
        "vercel_list_projects",
        "vercel_deploy_to_vercel",
    ]
    demo_payload = parse_demo_handoff(execution.handoffs[0].reason)
    assert demo_payload is not None
    assert demo_payload.stage == PROTOTYPE_SUMMARY_STAGE
    assert demo_payload.status == BLOCKED_STATUS
    assert "could not publish" in demo_payload.artifact.lower()
    assert "vercel deploy" in demo_payload.artifact.lower()


@pytest.mark.asyncio
async def test_dispatcher_handler_surfaces_blocked_prototype_status_honestly() -> None:
    handler = build_dispatcher_handler()

    execution = await handler(
        WorkflowContext(
            thread_key="discord-thread-1",
            current_agent=AgentRole.COORDINATOR,
            user_message="sure",
            transcript=(),
            trigger=DiscordTriggerContext(
                discord_server_id="discord-server-1",
                discord_user_id="user-1",
                channel_id=10,
                thread_id="discord-thread-1",
                message_id=101,
                thread_key="discord-thread-1",
                dispatch_reason="reply_to_bot",
            ),
            toolset=AgentToolset(),
            handoff_context=serialize_demo_handoff(
                stage=PROTOTYPE_SUMMARY_STAGE,
                status=BLOCKED_STATUS,
                artifact=(
                    "I translated the PRD into a prototype plan, but I could not "
                    "publish a live Vercel URL. The available Vercel tool only "
                    "returned manual deployment instructions: run `vercel deploy`."
                ),
            ),
        )
    )

    assert execution.handoffs == []
    assert execution.messages[0].agent is AgentRole.COORDINATOR
    assert "could not publish" in execution.messages[0].content.lower()
    assert "prototype draft is ready" not in execution.messages[0].content.lower()


def test_product_manager_prompt_spells_out_lenny_style_prd_sections() -> None:
    assert "Lenny Rachitsky-style PRD" in PRODUCT_MANAGER_SYSTEM_PROMPT
    assert "problem statement" in PRODUCT_MANAGER_SYSTEM_PROMPT.lower()
    assert "goals and non-goals" in PRODUCT_MANAGER_SYSTEM_PROMPT.lower()
    assert "success metrics" in PRODUCT_MANAGER_SYSTEM_PROMPT.lower()


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

    assert "".join(streamed_chunks) == execution.handoffs[0].reason
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

    assert execution.messages == []
    assert [handoff.target_agent for handoff in execution.handoffs] == [
        AgentRole.COORDINATOR
    ]
    assert "notion" in execution.handoffs[0].reason.lower()
    assert "connect" in execution.handoffs[0].reason.lower()


@pytest.mark.asyncio
async def test_user_researcher_handler_reports_failed_notion_initialization() -> None:
    handler = build_user_researcher_handler(
        model=_ToolCallingFakeListChatModel(
            responses=["This response should not be used when Notion auth fails."]
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
            toolset=AgentToolset(
                failures=(
                    IntegrationLoadFailure(
                        provider_id="notion",
                        provider_name="Notion",
                        status="active",
                        error="401 Unauthorized from Notion MCP",
                    ),
                )
            ),
        )
    )

    assert execution.messages == []
    assert [handoff.target_agent for handoff in execution.handoffs] == [
        AgentRole.COORDINATOR
    ]
    assert "notion is connected" in execution.handoffs[0].reason.lower()
    assert "reconnect" in execution.handoffs[0].reason.lower()


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

    assert execution.messages == []
    assert [handoff.target_agent for handoff in execution.handoffs] == [
        AgentRole.COORDINATOR
    ]
    assert execution.handoffs[0].reason.startswith("USER_RESEARCH_AGENT_OK")
    assert "notion" in execution.handoffs[0].reason.lower()


@pytest.mark.asyncio
async def test_product_designer_handler_returns_deep_agent_response() -> None:
    handler = build_product_designer_handler(
        model=_ToolCallingFakeListChatModel(
            responses=[
                "PRODUCT_DESIGNER_OK Prototype direction ready with a clickable "
                "Vercel handoff plan."
            ]
        )
    )

    execution = await handler(
        WorkflowContext(
            thread_key="discord-thread-1",
            current_agent=AgentRole.PRODUCT_DESIGNER,
            user_message="Design a lightweight clickable prototype for the new loop.",
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
        AgentRole.COORDINATOR
    ]
    assert execution.handoffs[0].reason.startswith("PRODUCT_DESIGNER_OK")


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

    assert execution.messages == []
    assert [handoff.target_agent for handoff in execution.handoffs] == [
        AgentRole.COORDINATOR
    ]
    assert execution.handoffs[0].reason.startswith("E2E_PLACEHOLDER_OK")
    assert "market analyst" in execution.handoffs[0].reason.lower()


def test_default_handlers_include_user_researcher() -> None:
    assert AgentRole.USER_RESEARCHER in default_agent_handlers()


def test_default_handlers_include_dispatcher() -> None:
    assert AgentRole.DISPATCHER in default_agent_handlers()


def test_default_handlers_include_product_designer() -> None:
    assert AgentRole.PRODUCT_DESIGNER in default_agent_handlers()
