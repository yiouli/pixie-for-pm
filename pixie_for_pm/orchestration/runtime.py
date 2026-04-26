from __future__ import annotations

from collections.abc import Mapping
from contextlib import AbstractAsyncContextManager
from pathlib import Path
from types import TracebackType

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from pixie_for_pm.agents.registry import AgentHandler, resolve_agent_handlers
from pixie_for_pm.domain.models import AgentRole, DispatchRequest, OrchestrationResult
from pixie_for_pm.orchestration.graph import (
    AsyncWorkflowGraph,
    build_initial_state,
    build_workflow_graph,
    deserialize_transcript,
)


class PixieOrchestrator:
    def __init__(
        self,
        checkpoint_path: Path,
        agent_handlers: Mapping[AgentRole, AgentHandler] | None = None,
    ) -> None:
        self._checkpoint_path = checkpoint_path
        self._handlers = resolve_agent_handlers(agent_handlers)
        self._checkpointer_context: (
            AbstractAsyncContextManager[AsyncSqliteSaver] | None
        ) = None
        self._graph: AsyncWorkflowGraph | None = None

    async def __aenter__(self) -> PixieOrchestrator:
        self._checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        checkpointer_context: AbstractAsyncContextManager[AsyncSqliteSaver] = (
            AsyncSqliteSaver.from_conn_string(str(self._checkpoint_path))
        )
        self._checkpointer_context = checkpointer_context
        checkpointer = await checkpointer_context.__aenter__()
        self._graph = build_workflow_graph(
            handlers=self._handlers, checkpointer=checkpointer
        )
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        checkpointer_context = self._checkpointer_context
        if checkpointer_context is not None:
            await checkpointer_context.__aexit__(exc_type, exc, tb)

    async def dispatch(self, request: DispatchRequest) -> OrchestrationResult:
        if self._graph is None:
            raise RuntimeError(
                "PixieOrchestrator must be entered before dispatching work."
            )

        state = build_initial_state(request)
        final_state = await self._graph.ainvoke(
            state,
            config={"configurable": {"thread_id": request.thread_key}},
        )
        return OrchestrationResult(
            thread_key=final_state["thread_key"],
            transcript=deserialize_transcript(final_state["turn_transcript"]),
        )
