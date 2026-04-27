from __future__ import annotations

import logging

import pytest
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.tools import ToolException

from pixie_for_pm.agents.deep_agent import _status_for_agent_event, run_deep_agent
from pixie_for_pm.domain.models import AgentRole, WorkflowContext
from pixie_for_pm.integrations.toolset import (
    AgentToolset,
    ConnectedIntegration,
    DiscordTriggerContext,
    IntegrationLoadFailure,
)


class _FailingDeepAgent:
    async def ainvoke(
        self,
        inputs: object,
        config: object | None = None,
    ) -> dict[str, object]:
        del inputs, config
        raise RuntimeError("missing content_updates parameter")


class _RetryingDeepAgent:
    def __init__(self) -> None:
        self.calls: list[list[BaseMessage]] = []

    async def ainvoke(
        self,
        inputs: object,
        config: object | None = None,
    ) -> dict[str, object]:
        del config
        if not isinstance(inputs, dict):
            raise AssertionError("expected dict inputs")
        messages = inputs.get("messages")
        if not isinstance(messages, list):
            raise AssertionError("expected list of messages")
        self.calls.append(messages)
        if len(self.calls) == 1:
            raise ToolException(
                " ".join(
                    (
                        '{"body":"{\\"object\\":\\"error\\",',
                        '\\"status\\":400,\\"code\\":\\"validation_error\\",',
                        '\\"message\\":\\"The \\\\\\"update_content\\\\\\"',
                        'command requires a \\\\\\"content_updates\\\\\\"',
                        'parameter.\\"}"}',
                    )
                )
            )
        return {"messages": [AIMessage(content="Recovered after retry")]}


class _SingleAttemptAgent:
    def __init__(self, *, fail_with_validation_error: bool) -> None:
        self.fail_with_validation_error = fail_with_validation_error
        self.calls: list[list[BaseMessage]] = []

    async def ainvoke(
        self,
        inputs: object,
        config: object | None = None,
    ) -> dict[str, object]:
        del config
        if not isinstance(inputs, dict):
            raise AssertionError("expected dict inputs")
        messages = inputs.get("messages")
        if not isinstance(messages, list):
            raise AssertionError("expected list of messages")
        self.calls.append(messages)
        if self.fail_with_validation_error:
            raise ToolException(
                'The "update_content" command requires a "content_updates" parameter.'
            )
        return {"messages": [AIMessage(content="Recovered with new agent")]}


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


@pytest.mark.asyncio
async def test_run_deep_agent_logs_failure_context(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "pixie_for_pm.agents.deep_agent.create_deep_agent",
        lambda **kwargs: _FailingDeepAgent(),
    )
    caplog.set_level(logging.ERROR, logger="pixie_for_pm.agents.deep_agent")

    with pytest.raises(RuntimeError, match="missing content_updates parameter"):
        await run_deep_agent(
            role=AgentRole.USER_RESEARCHER,
            agent_name="pixie_user_researcher",
            system_prompt="Investigate the issue.",
            context=WorkflowContext(
                thread_key="discord-thread-404",
                current_agent=AgentRole.USER_RESEARCHER,
                user_message="Update the Notion research synthesis.",
                transcript=(),
                trigger=DiscordTriggerContext(
                    discord_server_id="discord-server-404",
                    discord_user_id="user-404",
                    channel_id=12,
                    thread_id="discord-thread-404",
                    message_id=98,
                    thread_key="discord-thread-404",
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
                            tool_names=("notion_update_page",),
                        ),
                    ),
                    failures=(
                        IntegrationLoadFailure(
                            provider_id="github",
                            provider_name="GitHub",
                            status="active",
                            error="secondary provider failure",
                        ),
                    ),
                ),
            ),
            model="test-model",
        )

    assert "Deep agent run failed" in caplog.text
    assert "role=user_researcher" in caplog.text
    assert "thread_key=discord-thread-404" in caplog.text
    assert "integrations=notion" in caplog.text
    assert "tool_failures=github:secondary provider failure" in caplog.text


@pytest.mark.asyncio
async def test_run_deep_agent_retries_tool_validation_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent = _RetryingDeepAgent()
    monkeypatch.setattr(
        "pixie_for_pm.agents.deep_agent.create_deep_agent",
        lambda **kwargs: agent,
    )

    result = await run_deep_agent(
        role=AgentRole.USER_RESEARCHER,
        agent_name="pixie_user_researcher",
        system_prompt="Investigate the issue.",
        context=WorkflowContext(
            thread_key="discord-thread-405",
            current_agent=AgentRole.USER_RESEARCHER,
            user_message="Update the Notion research synthesis.",
            transcript=(),
            trigger=DiscordTriggerContext(
                discord_server_id="discord-server-405",
                discord_user_id="user-405",
                channel_id=13,
                thread_id="discord-thread-405",
                message_id=99,
                thread_key="discord-thread-405",
                dispatch_reason="direct_bot_mention",
            ),
            toolset=AgentToolset(),
        ),
        model="test-model",
    )

    assert result == "Recovered after retry"
    assert len(agent.calls) == 2
    retry_message = agent.calls[1][-1]
    assert "update_content" in retry_message.content
    assert "content_updates" in retry_message.content


@pytest.mark.asyncio
async def test_run_deep_agent_recreates_agent_for_validation_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created_agents: list[_SingleAttemptAgent] = []

    def _make_agent(**kwargs: object) -> _SingleAttemptAgent:
        del kwargs
        agent = _SingleAttemptAgent(fail_with_validation_error=len(created_agents) == 0)
        created_agents.append(agent)
        return agent

    monkeypatch.setattr(
        "pixie_for_pm.agents.deep_agent.create_deep_agent",
        _make_agent,
    )

    result = await run_deep_agent(
        role=AgentRole.USER_RESEARCHER,
        agent_name="pixie_user_researcher",
        system_prompt="Investigate the issue.",
        context=WorkflowContext(
            thread_key="discord-thread-406",
            current_agent=AgentRole.USER_RESEARCHER,
            user_message="Update the Notion research synthesis.",
            transcript=(),
            trigger=DiscordTriggerContext(
                discord_server_id="discord-server-406",
                discord_user_id="user-406",
                channel_id=14,
                thread_id="discord-thread-406",
                message_id=100,
                thread_key="discord-thread-406",
                dispatch_reason="direct_bot_mention",
            ),
            toolset=AgentToolset(),
        ),
        model="test-model",
    )

    assert result == "Recovered with new agent"
    assert len(created_agents) == 2
    assert len(created_agents[0].calls) == 1
    assert len(created_agents[1].calls) == 1
    retry_message = created_agents[1].calls[0][-1]
    assert "update_content" in retry_message.content
    assert "content_updates" in retry_message.content
