from __future__ import annotations

import logging
from collections.abc import Mapping
from contextlib import AbstractAsyncContextManager
from pathlib import Path
from types import TracebackType

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from pixie_for_pm.agents.registry import AgentHandler, resolve_agent_handlers
from pixie_for_pm.domain.models import (
    AgentRole,
    DispatchRequest,
    OrchestrationResult,
    PublicMessageEmitter,
    ResponseEmitter,
    StatusEmitter,
    emit_status_update,
)
from pixie_for_pm.integrations.toolset import (
    DiscordTriggerContext,
    EmptyToolsetInitializer,
    ToolsetInitializer,
)
from pixie_for_pm.orchestration.graph import (
    AsyncWorkflowGraph,
    build_initial_state,
    build_workflow_graph,
    deserialize_transcript,
)

logger = logging.getLogger(__name__)


class PixieOrchestrator:
    def __init__(
        self,
        checkpoint_path: Path,
        agent_handlers: Mapping[AgentRole, AgentHandler] | None = None,
        toolset_initializer: ToolsetInitializer | None = None,
    ) -> None:
        self._checkpoint_path = checkpoint_path
        self._handlers = resolve_agent_handlers(agent_handlers)
        self._toolset_initializer = toolset_initializer or EmptyToolsetInitializer()
        self._checkpointer_context: (
            AbstractAsyncContextManager[AsyncSqliteSaver] | None
        ) = None
        self._checkpointer: AsyncSqliteSaver | None = None

    async def __aenter__(self) -> PixieOrchestrator:
        self._checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        checkpointer_context: AbstractAsyncContextManager[AsyncSqliteSaver] = (
            AsyncSqliteSaver.from_conn_string(str(self._checkpoint_path))
        )
        self._checkpointer_context = checkpointer_context
        checkpointer = await checkpointer_context.__aenter__()
        self._checkpointer = checkpointer
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

    async def dispatch(
        self,
        request: DispatchRequest,
        *,
        status_emitter: StatusEmitter | None = None,
        response_emitter: ResponseEmitter | None = None,
        public_message_emitter: PublicMessageEmitter | None = None,
    ) -> OrchestrationResult:
        if self._checkpointer is None:
            raise RuntimeError(
                "PixieOrchestrator must be entered before dispatching work."
            )

        trigger = DiscordTriggerContext(
            request.message.discord_server_id,
            str(request.message.author_id),
            request.message.channel_id,
            request.message.thread_id,
            request.message.discord_message_id,
            request.thread_key,
            request.reason,
        )
        try:
            await emit_status_update(status_emitter, "Checking connected tools...")
            toolset = await self._toolset_initializer.initialize(
                trigger,
                status_emitter=status_emitter,
            )
            graph: AsyncWorkflowGraph = build_workflow_graph(
                handlers=self._handlers,
                checkpointer=self._checkpointer,
                trigger=trigger,
                status_emitter=status_emitter,
                response_emitter=response_emitter,
                public_message_emitter=public_message_emitter,
                toolset=toolset,
            )
            state = build_initial_state(request)
            final_state = await graph.ainvoke(
                state,
                config={"configurable": {"thread_id": request.thread_key}},
            )
        except Exception:
            logger.exception(
                "Orchestration dispatch failed target_agent=%s thread_key=%s "
                "discord_server_id=%s channel_id=%s thread_id=%s message_id=%s "
                "reason=%s",
                request.target_agent.value,
                request.thread_key,
                request.message.discord_server_id,
                request.message.channel_id,
                request.message.thread_id,
                request.message.discord_message_id,
                request.reason,
            )
            raise
        return OrchestrationResult(
            thread_key=final_state["thread_key"],
            transcript=deserialize_transcript(final_state["turn_transcript"]),
        )
