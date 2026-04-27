from collections.abc import AsyncIterator
from typing import cast

import pytest
from langchain_core.messages import AIMessage

from pixie_for_pm.agents.deep_agent import (
    DEEP_AGENT_RECURSION_LIMIT,
    _invoke_agent_with_status_events,
    _status_for_agent_event,
)
from pixie_for_pm.domain.models import AgentRole, WorkflowContext
from pixie_for_pm.integrations.toolset import AgentToolset, DiscordTriggerContext


class _InvokeOnlyAgent:
    def __init__(self) -> None:
        self.config: object | None = None

    async def ainvoke(
        self,
        input: object,
        config: object | None = None,
    ) -> dict[str, object]:
        del input
        self.config = config
        return {"messages": [AIMessage(content="done")]}


class _StreamingAgent:
    def __init__(self) -> None:
        self.config: object | None = None

    async def astream_events(
        self,
        input: object,
        config: object | None = None,
        *,
        version: str,
    ) -> AsyncIterator[dict[str, object]]:
        del input
        assert version == "v2"
        self.config = config
        yield {
            "event": "on_chain_end",
            "name": "test_agent",
            "data": {"output": {"messages": [AIMessage(content="done")]}},
        }


def _context(*, streamed: bool) -> WorkflowContext:
    status_emitter = (lambda _status: None) if streamed else None
    return WorkflowContext(
        thread_key="discord-thread-1",
        current_agent=AgentRole.USER_RESEARCHER,
        user_message="Summarize the findings.",
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
        status_emitter=status_emitter,
    )


@pytest.mark.asyncio
async def test_invoke_agent_with_status_events_passes_recursion_limit_to_ainvoke() -> (
    None
):
    agent = _InvokeOnlyAgent()

    result = await _invoke_agent_with_status_events(
        agent=agent,
        context=_context(streamed=False),
        role=AgentRole.USER_RESEARCHER,
        inputs={"messages": []},
        agent_name="test_agent",
    )
    messages = cast(list[AIMessage], result["messages"])

    assert messages[0].content == "done"
    assert agent.config == {"recursion_limit": DEEP_AGENT_RECURSION_LIMIT}


@pytest.mark.asyncio
async def test_invoke_agent_with_status_events_passes_recursion_limit_to_astream_events() -> (
    None
):
    agent = _StreamingAgent()

    result = await _invoke_agent_with_status_events(
        agent=agent,
        context=_context(streamed=True),
        role=AgentRole.USER_RESEARCHER,
        inputs={"messages": []},
        agent_name="test_agent",
    )
    messages = cast(list[AIMessage], result["messages"])

    assert messages[0].content == "done"
    assert agent.config == {"recursion_limit": DEEP_AGENT_RECURSION_LIMIT}


@pytest.mark.parametrize(
    ("role", "subject"),
    [
        (AgentRole.PRODUCT_MANAGER, "Product manager"),
        (AgentRole.USER_RESEARCHER, "User researcher"),
        (AgentRole.PRODUCT_DESIGNER, "Product designer"),
    ],
)
def test_status_for_agent_event_emits_tool_progress_updates(
    role: AgentRole,
    subject: str,
) -> None:
    assert _status_for_agent_event({"event": "on_chat_model_start"}, role=role) == (
        f"{subject} is reasoning..."
    )
    assert (
        _status_for_agent_event(
            {"event": "on_tool_start", "name": "notion_search"},
            role=role,
        )
        == f"{subject} is using notion search..."
    )
    assert (
        _status_for_agent_event(
            {"event": "on_tool_end", "name": "notion_search"},
            role=role,
        )
        == f"{subject} is reviewing results from notion search..."
    )
    assert (
        _status_for_agent_event(
            {
                "event": "on_chat_model_end",
                "data": {"output": AIMessage(content="Done")},
            },
            role=role,
        )
        == f"{subject} is drafting the response..."
    )
