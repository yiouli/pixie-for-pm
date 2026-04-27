from __future__ import annotations

from collections.abc import Awaitable, Callable

from langchain_core.language_models.chat_models import BaseChatModel

from pixie_for_pm.agents.deep_agent import (
    DEFAULT_DEEP_AGENT_MODEL,
    build_deep_agent_handler,
)
from pixie_for_pm.domain.models import AgentExecution, AgentRole, WorkflowContext

DEFAULT_PRODUCT_MANAGER_MODEL = DEFAULT_DEEP_AGENT_MODEL
PRODUCT_MANAGER_AGENT_NAME = "pixie_product_manager"

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
    return build_deep_agent_handler(
        role=AgentRole.PRODUCT_MANAGER,
        agent_name=PRODUCT_MANAGER_AGENT_NAME,
        system_prompt=_SYSTEM_PROMPT,
        model=model,
        openai_api_key=openai_api_key,
    )
