from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Any, cast

from deepagents import create_deep_agent
from langchain.chat_models import init_chat_model
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, HumanMessage

from pixie_for_pm.domain.models import (
    AgentExecution,
    AgentMessage,
    AgentRole,
    WorkflowContext,
    emit_response_chunk,
    emit_status_update,
)

DEFAULT_DEEP_AGENT_MODEL = "openai:gpt-5.4"

ExecutionContextBuilder = Callable[[WorkflowContext], str | None]
PreflightCheck = Callable[[WorkflowContext], AgentExecution | None]


def build_deep_agent_handler(
    *,
    role: AgentRole,
    agent_name: str,
    system_prompt: str,
    model: str | BaseChatModel = DEFAULT_DEEP_AGENT_MODEL,
    openai_api_key: str | None = None,
    execution_context_builder: ExecutionContextBuilder | None = None,
    preflight_check: PreflightCheck | None = None,
) -> Callable[[WorkflowContext], Awaitable[AgentExecution]]:
    async def _handler(context: WorkflowContext) -> AgentExecution:
        if preflight_check is not None:
            preflight_result = preflight_check(context)
            if preflight_result is not None:
                return preflight_result

        agent = create_deep_agent(
            model=_resolve_model(model, openai_api_key=openai_api_key),
            tools=list(context.toolset.as_langgraph_tools()),
            system_prompt=system_prompt,
            checkpointer=False,
            name=agent_name,
        )
        result = await _invoke_agent_with_status_events(
            agent=agent,
            context=context,
            role=role,
            inputs={
                "messages": _build_messages(
                    context,
                    execution_context_builder=execution_context_builder,
                )
            },
            agent_name=agent_name,
        )
        content = _extract_final_response_text(
            cast(Sequence[BaseMessage], result.get("messages", []))
        )
        return AgentExecution(
            messages=[
                AgentMessage(
                    agent=role,
                    content=content,
                )
            ]
        )

    return _handler


def _resolve_model(
    model: str | BaseChatModel,
    *,
    openai_api_key: str | None,
) -> str | BaseChatModel:
    if isinstance(model, str) and model.startswith("openai:") and openai_api_key:
        return init_chat_model(model=model, api_key=openai_api_key)
    return model


async def _invoke_agent_with_status_events(
    *,
    agent: Any,
    context: WorkflowContext,
    role: AgentRole,
    inputs: dict[str, object],
    agent_name: str,
) -> dict[str, object]:
    if context.status_emitter is None and context.response_emitter is None:
        return cast(dict[str, object], await agent.ainvoke(cast(Any, inputs)))

    final_output: dict[str, object] | None = None
    last_status: str | None = None
    async for event in agent.astream_events(cast(Any, inputs), version="v2"):
        text_delta = _stream_text_delta(event)
        if text_delta is not None:
            await emit_response_chunk(context.response_emitter, text_delta)

        status = _status_for_agent_event(event, role=role)
        if status is not None and status != last_status:
            await emit_status_update(context.status_emitter, status)
            last_status = status

        if event.get("event") == "on_chain_end" and event.get("name") == agent_name:
            data = event.get("data")
            if not isinstance(data, dict):
                continue

            output = data.get("output")
            if isinstance(output, dict):
                final_output = cast(dict[str, object], output)

    if final_output is None:
        raise RuntimeError(f"{role.label.capitalize()} agent produced no final output.")

    return final_output


def _stream_text_delta(event: Mapping[str, object]) -> str | None:
    if event.get("event") != "on_chat_model_stream":
        return None

    data = event.get("data")
    if not isinstance(data, dict):
        return None

    chunk = data.get("chunk")
    if not isinstance(chunk, AIMessageChunk):
        return None

    if chunk.tool_call_chunks:
        return None

    text_delta = _coerce_text_content(chunk.content, strip=False)
    if text_delta == "":
        return None

    return text_delta


def _status_for_agent_event(
    event: Mapping[str, object],
    *,
    role: AgentRole,
) -> str | None:
    subject = role.label.capitalize()
    event_type = event.get("event")
    if event_type == "on_chat_model_start":
        return f"{subject} is reasoning..."

    if event_type != "on_chat_model_end":
        return None

    output_message = _event_output_message(event)
    if output_message is None:
        return None

    if output_message.tool_calls:
        tool_name = _tool_call_name(output_message.tool_calls)
        if tool_name is not None:
            return f"{subject} is preparing to use {tool_name}..."
        return f"{subject} is preparing to use a tool..."

    if _coerce_text_content(output_message.content, strip=True) != "":
        return f"{subject} is drafting the response..."

    return None


def _event_output_message(event: Mapping[str, object]) -> AIMessage | None:
    data = event.get("data")
    if not isinstance(data, dict):
        return None

    output = data.get("output")
    if isinstance(output, AIMessage):
        return output

    return None


def _tool_call_name(tool_calls: object) -> str | None:
    if not isinstance(tool_calls, list) or not tool_calls:
        return None

    first_call = tool_calls[0]
    if not isinstance(first_call, dict):
        return None

    name = first_call.get("name")
    if not isinstance(name, str) or name == "":
        return None

    return name.replace("_", " ")


def _build_messages(
    context: WorkflowContext,
    *,
    execution_context_builder: ExecutionContextBuilder | None,
) -> list[BaseMessage]:
    messages: list[BaseMessage] = []
    for transcript_message in context.transcript:
        messages.append(
            AIMessage(
                content=(
                    f"Previous {transcript_message.agent.label} response: "
                    f"{transcript_message.content}"
                )
            )
        )
    if execution_context_builder is not None:
        execution_context = execution_context_builder(context)
        if execution_context is not None and execution_context.strip() != "":
            messages.append(HumanMessage(content=execution_context))
    messages.append(HumanMessage(content=context.user_message))
    return messages


def _extract_final_response_text(messages: Sequence[BaseMessage]) -> str:
    for message in reversed(messages):
        if isinstance(message, AIMessage):
            content = _coerce_text_content(message.content, strip=True)
            if content != "":
                return content
    raise RuntimeError("Agent produced no user-visible response.")


def _coerce_text_content(content: object, *, strip: bool) -> str:
    if isinstance(content, str):
        return content.strip() if strip else content
    if isinstance(content, list):
        text_parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                normalized = item.strip() if strip else item
                if normalized != "":
                    text_parts.append(normalized)
            elif isinstance(item, dict):
                text_value = item.get("text")
                if isinstance(text_value, str):
                    normalized = text_value.strip() if strip else text_value
                    if normalized != "":
                        text_parts.append(normalized)
        if strip:
            return "\n".join(text_parts).strip()
        return "".join(text_parts)
    return ""
