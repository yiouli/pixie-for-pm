from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from operator import add
from typing import Annotated, Any, Literal, Protocol, TypedDict, cast

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import END, START, StateGraph

from pixie_for_pm.agents.registry import AgentHandler
from pixie_for_pm.domain.models import (
    AgentExecution,
    AgentHandoff,
    AgentMessage,
    AgentRole,
    DispatchRequest,
    PublicMessageEmitter,
    ResponseEmitter,
    StatusEmitter,
    WorkflowContext,
    emit_public_message,
    emit_status_update,
)
from pixie_for_pm.integrations.toolset import AgentToolset, DiscordTriggerContext


class SerializedAgentMessage(TypedDict):
    agent: str
    content: str


class SerializedAgentHandoff(TypedDict):
    source_agent: str
    target_agent: str
    reason: str


class WorkflowState(TypedDict):
    thread_key: str
    user_message: str
    current_agent: str
    dispatch_reason: str
    current_handoff_reason: str | None
    transcript: Annotated[list[SerializedAgentMessage], add]
    turn_transcript: list[SerializedAgentMessage]
    turn_handoffs: list[SerializedAgentHandoff]
    pending_handoffs: list[SerializedAgentHandoff]


class AsyncWorkflowGraph(Protocol):
    async def ainvoke(
        self,
        input: WorkflowState,
        config: object | None = None,
    ) -> WorkflowState: ...


AgentNode = Callable[[WorkflowState], Awaitable[dict[str, object]]]


def build_initial_state(request: DispatchRequest) -> WorkflowState:
    return WorkflowState(
        thread_key=request.thread_key,
        user_message=request.message.content,
        current_agent=request.target_agent.value,
        dispatch_reason=request.reason,
        current_handoff_reason=None,
        transcript=[],
        turn_transcript=[],
        turn_handoffs=[],
        pending_handoffs=[],
    )


def deserialize_transcript(
    transcript: list[SerializedAgentMessage],
) -> list[AgentMessage]:
    return [
        AgentMessage(
            agent=AgentRole(message["agent"]),
            content=message["content"],
        )
        for message in transcript
    ]


def _serialize_messages(messages: list[AgentMessage]) -> list[SerializedAgentMessage]:
    return [
        SerializedAgentMessage(
            agent=message.agent.value,
            content=message.content,
        )
        for message in messages
    ]


def _serialize_handoffs(handoffs: list[AgentHandoff]) -> list[SerializedAgentHandoff]:
    return [
        SerializedAgentHandoff(
            source_agent=handoff.source_agent.value,
            target_agent=handoff.target_agent.value,
            reason=handoff.reason,
        )
        for handoff in handoffs
    ]


def _to_context(
    state: WorkflowState,
    role: AgentRole,
    *,
    trigger: DiscordTriggerContext,
    status_emitter: StatusEmitter | None,
    response_emitter: ResponseEmitter | None,
    public_message_emitter: PublicMessageEmitter | None,
    toolset: AgentToolset,
) -> WorkflowContext:
    return WorkflowContext(
        state["thread_key"],
        role,
        state["user_message"],
        tuple(deserialize_transcript(state["transcript"])),
        trigger,
        toolset,
        status_emitter,
        response_emitter,
        public_message_emitter,
        state["current_handoff_reason"],
    )


def _agent_node(
    role: AgentRole,
    handlers: Mapping[AgentRole, AgentHandler],
    *,
    trigger: DiscordTriggerContext,
    status_emitter: StatusEmitter | None,
    response_emitter: ResponseEmitter | None,
    public_message_emitter: PublicMessageEmitter | None,
    toolset: AgentToolset,
) -> AgentNode:
    async def _run_agent(state: WorkflowState) -> dict[str, object]:
        await emit_status_update(
            status_emitter,
            f"Analyzing with {role.label}...",
        )
        execution: AgentExecution = await handlers[role](
            _to_context(
                state=state,
                role=role,
                trigger=trigger,
                status_emitter=status_emitter,
                response_emitter=response_emitter,
                public_message_emitter=public_message_emitter,
                toolset=toolset,
            )
        )
        _validate_handoffs(role, execution.handoffs)
        if execution.messages and execution.handoffs:
            for message in execution.messages:
                await emit_public_message(public_message_emitter, message.content)
        serialized_messages = _serialize_messages(execution.messages)
        serialized_handoffs = _serialize_handoffs(execution.handoffs)
        return {
            "transcript": serialized_messages,
            "turn_transcript": state["turn_transcript"] + serialized_messages,
            "turn_handoffs": state["turn_handoffs"] + serialized_handoffs,
            "pending_handoffs": serialized_handoffs,
        }

    return _run_agent


def _route_current_agent(state: WorkflowState) -> Literal[
    "dispatcher",
    "product_manager",
    "market_analyst",
    "user_researcher",
    "product_designer",
]:
    return cast(
        Literal[
            "dispatcher",
            "product_manager",
            "market_analyst",
            "user_researcher",
            "product_designer",
        ],
        state["current_agent"],
    )


def _validate_handoffs(role: AgentRole, handoffs: list[AgentHandoff]) -> None:
    for handoff in handoffs:
        if handoff.source_agent is not role:
            raise ValueError("Agent handoff source must match the current agent.")
        if handoff.target_agent is AgentRole.DISPATCHER:
            raise ValueError("Agents cannot hand off work back to dispatcher.")


def _route_after_agent(state: WorkflowState) -> str:
    if state["pending_handoffs"]:
        return "handoff"
    return END


def _dispatch_node(state: WorkflowState) -> dict[str, object]:
    del state
    return {
        "turn_transcript": [],
        "turn_handoffs": [],
        "current_handoff_reason": None,
    }


async def _handoff_node(state: WorkflowState) -> dict[str, object]:
    return {
        "current_agent": AgentRole(state["pending_handoffs"][0]["target_agent"]).value,
        "current_handoff_reason": state["pending_handoffs"][0]["reason"],
        "pending_handoffs": state["pending_handoffs"][1:],
    }


def _build_handoff_node(
    status_emitter: StatusEmitter | None,
) -> AgentNode:
    async def _run_handoff(state: WorkflowState) -> dict[str, object]:
        next_handoff = state["pending_handoffs"][0]
        target_agent = AgentRole(next_handoff["target_agent"])
        await emit_status_update(
            status_emitter,
            f"Handing off to {target_agent.label}...",
        )
        return await _handoff_node(state)

    return _run_handoff


def build_workflow_graph(
    handlers: Mapping[AgentRole, AgentHandler],
    checkpointer: AsyncSqliteSaver,
    *,
    trigger: DiscordTriggerContext,
    status_emitter: StatusEmitter | None = None,
    response_emitter: ResponseEmitter | None = None,
    public_message_emitter: PublicMessageEmitter | None = None,
    toolset: AgentToolset,
) -> AsyncWorkflowGraph:
    builder = StateGraph(WorkflowState)
    builder.add_node("dispatch", _dispatch_node)
    builder.add_node("handoff", cast(Any, _build_handoff_node(status_emitter)))

    for role in AgentRole:
        builder.add_node(
            role.value,
            cast(
                Any,
                _agent_node(
                    role=role,
                    handlers=handlers,
                    trigger=trigger,
                    status_emitter=status_emitter,
                    response_emitter=response_emitter,
                    public_message_emitter=public_message_emitter,
                    toolset=toolset,
                ),
            ),
        )

    builder.add_edge(START, "dispatch")
    builder.add_conditional_edges("dispatch", _route_current_agent)

    for role in AgentRole:
        builder.add_conditional_edges(role.value, _route_after_agent)

    builder.add_conditional_edges("handoff", _route_current_agent)

    return cast(AsyncWorkflowGraph, builder.compile(checkpointer=checkpointer))
