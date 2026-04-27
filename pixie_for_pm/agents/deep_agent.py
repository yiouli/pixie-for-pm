from __future__ import annotations

import logging
import re
from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Any, cast

from deepagents import create_deep_agent
from langchain.chat_models import init_chat_model
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, HumanMessage
from langchain_core.tools import ToolException

from pixie_for_pm.domain.models import (
    AgentExecution,
    AgentMessage,
    AgentRole,
    WorkflowContext,
    emit_response_chunk,
    emit_status_update,
)

DEFAULT_DEEP_AGENT_MODEL = "openai:gpt-5.4"
DEEP_AGENT_RECURSION_LIMIT = 100

logger = logging.getLogger(__name__)

_REQUIRED_TOOL_PARAMETER_PATTERN = re.compile(
    r'The\s+"?(?P<tool>[^"\\]+)"?\s+command\s+requires\s+a\s+"?(?P<parameter>[^"\\]+)"?\s+parameter'
)
_INVALID_URL_PATTERN = re.compile(r"Invalid URL:\s*(?P<url>\S+)")

ExecutionContextBuilder = Callable[[WorkflowContext], str | None]
PreflightCheck = Callable[[WorkflowContext], AgentExecution | None]


async def run_deep_agent(
    *,
    role: AgentRole,
    agent_name: str,
    system_prompt: str,
    context: WorkflowContext,
    model: str | BaseChatModel = DEFAULT_DEEP_AGENT_MODEL,
    openai_api_key: str | None = None,
    execution_context_builder: ExecutionContextBuilder | None = None,
) -> str:
    messages = _build_messages(
        context,
        execution_context_builder=execution_context_builder,
    )
    resolved_model = _resolve_model(model, openai_api_key=openai_api_key)
    try:
        result = await _invoke_agent_with_status_events(
            agent=_create_agent(
                resolved_model=resolved_model,
                context=context,
                system_prompt=system_prompt,
                agent_name=agent_name,
            ),
            context=context,
            role=role,
            inputs={"messages": messages},
            agent_name=agent_name,
        )
    except Exception as exc:
        retry_guidance = _build_tool_validation_retry_guidance(exc)
        if retry_guidance is None:
            _log_deep_agent_failure(
                exc,
                role=role,
                agent_name=agent_name,
                context=context,
            )
            raise

        logger.warning(
            "Retrying deep agent after tool validation failure role=%s agent_name=%s "
            "thread_key=%s tool=%s parameter=%s",
            role.value,
            agent_name,
            context.thread_key,
            retry_guidance[0],
            retry_guidance[1],
        )
        try:
            result = await _invoke_agent_with_status_events(
                agent=_create_agent(
                    resolved_model=resolved_model,
                    context=context,
                    system_prompt=system_prompt,
                    agent_name=agent_name,
                ),
                context=context,
                role=role,
                inputs={
                    "messages": [
                        *messages,
                        HumanMessage(content=retry_guidance[2]),
                    ]
                },
                agent_name=agent_name,
            )
        except Exception as retry_exc:
            _log_deep_agent_failure(
                retry_exc,
                role=role,
                agent_name=agent_name,
                context=context,
            )
            raise
    return _extract_final_response_text(
        cast(Sequence[BaseMessage], result.get("messages", []))
    )


def _create_agent(
    *,
    resolved_model: str | BaseChatModel,
    context: WorkflowContext,
    system_prompt: str,
    agent_name: str,
) -> Any:
    return create_deep_agent(
        model=resolved_model,
        tools=list(context.toolset.as_langgraph_tools()),
        system_prompt=system_prompt,
        checkpointer=False,
        name=agent_name,
    )


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

        content = await run_deep_agent(
            context=context,
            role=role,
            agent_name=agent_name,
            system_prompt=system_prompt,
            model=model,
            openai_api_key=openai_api_key,
            execution_context_builder=execution_context_builder,
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
        return cast(
            dict[str, object],
            await agent.ainvoke(cast(Any, inputs), config=_deep_agent_config()),
        )

    final_output: dict[str, object] | None = None
    last_status: str | None = None
    async for event in agent.astream_events(
        cast(Any, inputs),
        config=_deep_agent_config(),
        version="v2",
    ):
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

    if event_type == "on_tool_start":
        tool_name = _event_name(event)
        if tool_name is not None:
            return f"{subject} is using {tool_name}..."
        return f"{subject} is using a tool..."

    if event_type == "on_tool_end":
        tool_name = _event_name(event)
        if tool_name is not None:
            return f"{subject} is reviewing results from {tool_name}..."
        return f"{subject} is reviewing tool results..."

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


def _event_name(event: Mapping[str, object]) -> str | None:
    name = event.get("name")
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
    if context.handoff_context is not None and context.handoff_context.strip() != "":
        messages.append(
            HumanMessage(
                content=(
                    "Internal handoff context from the prior agent:\n"
                    f"{context.handoff_context}"
                )
            )
        )
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


def _build_tool_validation_retry_guidance(
    exc: Exception,
) -> tuple[str, str, str] | None:
    if not isinstance(exc, ToolException):
        return None

    normalized_message = str(exc).replace('\\\\"', '"').replace('\\"', '"')
    match = _REQUIRED_TOOL_PARAMETER_PATTERN.search(normalized_message)
    if match is None:
        invalid_url_match = _INVALID_URL_PATTERN.search(normalized_message)
        if invalid_url_match is not None:
            invalid_url = invalid_url_match.group("url").rstrip('".,')
            return (
                "unknown",
                "identifier",
                (
                    "Your last tool call failed validation because one of the values "
                    "was invalid. Retry the same step, but do not reuse the failing "
                    f"value `{invalid_url}`. Search Notion first, then pass the exact "
                    "page or database ID, or the canonical https://www.notion.so/... "
                    "URL returned by `notion_notion-search` or a prior Notion tool "
                    "result. Do not invent `notion://` locators, local docs paths, "
                    "or slugs."
                ),
            )

        if "validation_error" not in normalized_message.lower():
            return None

        return (
            "unknown",
            "unknown",
            (
                "Your last tool call failed validation. Retry the same step after "
                "repairing the invalid arguments. Reuse exact identifiers and values "
                "from prior tool output instead of inventing them. Error: "
                f"{_summarize_validation_error(normalized_message)}"
            ),
        )

    tool_name = match.group("tool")
    parameter_name = match.group("parameter")
    return (
        tool_name,
        parameter_name,
        (
            "Your last tool call failed validation. Retry the same step and inspect "
            f"the tool schema carefully. The `{tool_name}` tool requires the "
            f"`{parameter_name}` parameter. Include every required parameter exactly "
            "as defined by the tool before continuing."
        ),
    )


def _summarize_validation_error(message: str, *, max_length: int = 240) -> str:
    compact_message = " ".join(message.split())
    if len(compact_message) <= max_length:
        return compact_message
    return f"{compact_message[: max_length - 3]}..."


def _deep_agent_config() -> dict[str, int]:
    return {"recursion_limit": DEEP_AGENT_RECURSION_LIMIT}


def _log_deep_agent_failure(
    exc: Exception,
    *,
    role: AgentRole,
    agent_name: str,
    context: WorkflowContext,
) -> None:
    logger.exception(
        "Deep agent run failed role=%s agent_name=%s thread_key=%s "
        "discord_server_id=%s channel_id=%s thread_id=%s message_id=%s "
        "dispatch_reason=%s integrations=%s tool_failures=%s",
        role.value,
        agent_name,
        context.thread_key,
        context.trigger.discord_server_id,
        context.trigger.channel_id,
        context.trigger.thread_id,
        context.trigger.message_id,
        context.trigger.dispatch_reason,
        _format_connected_integrations(context),
        _format_tool_failures(context),
        exc_info=exc,
    )


def _format_connected_integrations(context: WorkflowContext) -> str:
    provider_ids = [
        integration.provider_id for integration in context.toolset.integrations
    ]
    if not provider_ids:
        return "none"
    return ",".join(provider_ids)


def _format_tool_failures(context: WorkflowContext) -> str:
    failures = [
        f"{failure.provider_id}:{failure.error}" for failure in context.toolset.failures
    ]
    if not failures:
        return "none"
    return " | ".join(failures)


__all__ = [
    "DEEP_AGENT_RECURSION_LIMIT",
    "DEFAULT_DEEP_AGENT_MODEL",
    "ExecutionContextBuilder",
    "PreflightCheck",
    "build_deep_agent_handler",
    "run_deep_agent",
]
