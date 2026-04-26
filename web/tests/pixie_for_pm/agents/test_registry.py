import pytest

from pixie_for_pm.agents.registry import default_agent_handlers
from pixie_for_pm.domain.models import AgentRole, WorkflowContext


@pytest.mark.asyncio
async def test_placeholder_handlers_return_stable_e2e_marker() -> None:
    handler = default_agent_handlers()[AgentRole.PRODUCT_MANAGER]

    execution = await handler(
        WorkflowContext(
            thread_key="discord-thread-1",
            current_agent=AgentRole.PRODUCT_MANAGER,
            user_message="Can you help me test the Discord bot?",
            transcript=(),
        )
    )

    assert execution.messages[0].content.startswith("E2E_PLACEHOLDER_OK")
    assert "product manager" in execution.messages[0].content.lower()
