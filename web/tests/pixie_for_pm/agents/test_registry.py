import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel

from pixie_for_pm.agents.registry import (
    build_product_manager_handler,
    default_agent_handlers,
)
from pixie_for_pm.domain.models import AgentRole, WorkflowContext
from pixie_for_pm.integrations.toolset import AgentToolset, DiscordTriggerContext


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
async def test_default_handlers_keep_placeholder_contract_for_non_pm_roles() -> None:
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
