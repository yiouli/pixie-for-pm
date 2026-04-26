import pytest

from pixie_for_pm.agents.registry import default_agent_handlers
from pixie_for_pm.domain.models import AgentRole, WorkflowContext
from pixie_for_pm.integrations.toolset import AgentToolset, DiscordTriggerContext


@pytest.mark.asyncio
async def test_placeholder_handlers_return_stable_e2e_marker() -> None:
    handler = default_agent_handlers()[AgentRole.PRODUCT_MANAGER]

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

    assert execution.messages[0].content.startswith("E2E_PLACEHOLDER_OK")
    assert "product manager" in execution.messages[0].content.lower()
