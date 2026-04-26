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
    WorkflowContext,
)


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
    transcript: Annotated[list[SerializedAgentMessage], add]
    turn_transcript: list[SerializedAgentMessage]
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
        transcript=[],
        turn_transcript=[],
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


def _to_context(state: WorkflowState, role: AgentRole) -> WorkflowContext:
    return WorkflowContext(
        thread_key=state["thread_key"],
        current_agent=role,
        user_message=state["user_message"],
        transcript=tuple(deserialize_transcript(state["transcript"])),
    )


def _agent_node(
    role: AgentRole, handlers: Mapping[AgentRole, AgentHandler]
) -> AgentNode:
    async def _run_agent(state: WorkflowState) -> dict[str, object]:
        execution: AgentExecution = await handlers[role](
            _to_context(state=state, role=role)
        )
        serialized_messages = _serialize_messages(execution.messages)
        return {
            "transcript": serialized_messages,
            "turn_transcript": state["turn_transcript"] + serialized_messages,
            "pending_handoffs": _serialize_handoffs(execution.handoffs),
        }

    return _run_agent


def _route_current_agent(state: WorkflowState) -> Literal[
    "product_manager",
    "market_analyst",
    "user_researcher",
    "data_scientist",
    "product_designer",
]:
    return cast(
        Literal[
            "product_manager",
            "market_analyst",
            "user_researcher",
            "data_scientist",
            "product_designer",
        ],
        state["current_agent"],
    )


def _route_after_agent(state: WorkflowState) -> str:
    if state["pending_handoffs"]:
        return "handoff"
    return END


def _dispatch_node(state: WorkflowState) -> dict[str, object]:
    return {"turn_transcript": []}


async def _handoff_node(state: WorkflowState) -> dict[str, object]:
    next_handoff = state["pending_handoffs"][0]
    source_agent = AgentRole(next_handoff["source_agent"])
    target_agent = AgentRole(next_handoff["target_agent"])
    remaining_handoffs = state["pending_handoffs"][1:]
    handoff_message = AgentMessage(
        agent=source_agent,
        content=f"Handoff to {target_agent.label}: {next_handoff['reason']}",
    )
    serialized_message = _serialize_messages([handoff_message])
    return {
        "current_agent": target_agent.value,
        "pending_handoffs": remaining_handoffs,
        "transcript": serialized_message,
        "turn_transcript": state["turn_transcript"] + serialized_message,
    }


def build_workflow_graph(
    handlers: Mapping[AgentRole, AgentHandler],
    checkpointer: AsyncSqliteSaver,
) -> AsyncWorkflowGraph:
    builder = StateGraph(WorkflowState)
    builder.add_node("dispatch", _dispatch_node)
    builder.add_node("handoff", _handoff_node)

    for role in AgentRole:
        builder.add_node(
            role.value, cast(Any, _agent_node(role=role, handlers=handlers))
        )

    builder.add_edge(START, "dispatch")
    builder.add_conditional_edges("dispatch", _route_current_agent)

    for role in AgentRole:
        builder.add_conditional_edges(role.value, _route_after_agent)

    builder.add_conditional_edges("handoff", _route_current_agent)

    return cast(AsyncWorkflowGraph, builder.compile(checkpointer=checkpointer))
