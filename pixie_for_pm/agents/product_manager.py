from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from typing import Any, cast

from deepagents import create_deep_agent
from langchain.chat_models import init_chat_model
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from pixie_for_pm.domain.models import (
    AgentExecution,
    AgentMessage,
    AgentRole,
    WorkflowContext,
)

DEFAULT_PRODUCT_MANAGER_MODEL = "openai:gpt-5.4"

_SYSTEM_PROMPT = """
You are Pixie's product manager agent.

Respond like a senior PM working inside a cross-functional product team.
Be concrete, concise, and execution-oriented.
Use any connected tools when they materially improve the answer.
When you reference prior internal context, synthesize it instead of repeating it verbatim.
""".strip()


def build_product_manager_handler(
    *,
    model: str | BaseChatModel = DEFAULT_PRODUCT_MANAGER_MODEL,
    openai_api_key: str | None = None,
) -> Callable[[WorkflowContext], Awaitable[AgentExecution]]:
    async def _handler(context: WorkflowContext) -> AgentExecution:
        agent = create_deep_agent(
            model=_resolve_model(model, openai_api_key=openai_api_key),
            tools=list(context.toolset.as_langgraph_tools()),
            system_prompt=_SYSTEM_PROMPT,
            checkpointer=False,
            name="pixie_product_manager",
        )
        result = cast(
            dict[str, object],
            await agent.ainvoke(cast(Any, {"messages": _build_messages(context)})),
        )
        content = _extract_final_response_text(
            cast(Sequence[BaseMessage], result.get("messages", []))
        )
        return AgentExecution(
            messages=[
                AgentMessage(
                    agent=AgentRole.PRODUCT_MANAGER,
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


def _build_messages(context: WorkflowContext) -> list[BaseMessage]:
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
    messages.append(HumanMessage(content=context.user_message))
    return messages


def _extract_final_response_text(messages: Sequence[BaseMessage]) -> str:
    for message in reversed(messages):
        if isinstance(message, AIMessage):
            content = _coerce_text_content(message.content)
            if content != "":
                return content
    raise RuntimeError("Product manager agent produced no user-visible response.")


def _coerce_text_content(content: object) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        text_parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                stripped = item.strip()
                if stripped != "":
                    text_parts.append(stripped)
            elif isinstance(item, dict):
                text_value = item.get("text")
                if isinstance(text_value, str):
                    stripped = text_value.strip()
                    if stripped != "":
                        text_parts.append(stripped)
        return "\n".join(text_parts).strip()
    return ""
