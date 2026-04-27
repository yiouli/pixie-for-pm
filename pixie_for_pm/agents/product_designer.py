from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import replace

from langchain_core.language_models.chat_models import BaseChatModel

from pixie_for_pm.agents.deep_agent import DEFAULT_DEEP_AGENT_MODEL, run_deep_agent
from pixie_for_pm.agents.demo_flow import (
    BLOCKED_STATUS,
    PROTOTYPE_BRIEF_STAGE,
    PROTOTYPE_SUMMARY_STAGE,
    parse_demo_handoff,
    serialize_demo_handoff,
)
from pixie_for_pm.domain.models import (
    AgentExecution,
    AgentHandoff,
    AgentMessage,
    AgentRole,
    WorkflowContext,
)
from pixie_for_pm.integrations.toolset import ConnectedIntegration

DEFAULT_PRODUCT_DESIGNER_MODEL = DEFAULT_DEEP_AGENT_MODEL
PRODUCT_DESIGNER_AGENT_NAME = "pixie_product_designer"

PRODUCT_DESIGNER_SYSTEM_PROMPT = """
You are Pixie's product designer agent.

Translate product direction into a clear user flow, interaction model, and visual prototype plan.
Be concrete and product-minded, not decorative.
Use Vercel tools when they are available to publish or update a clickable prototype.
If Vercel is not connected, say exactly what prototype work you completed
and what publish step is blocked.

When a PM hands you a PRD, turn it into:
- the core user journey
- the critical screens and states
- the interaction model for the retention loop
- a concise summary of the clickable prototype outcome
""".strip()


def build_product_designer_handler(
    *,
    model: str | BaseChatModel = DEFAULT_PRODUCT_DESIGNER_MODEL,
    openai_api_key: str | None = None,
) -> Callable[[WorkflowContext], Awaitable[AgentExecution]]:
    async def _handler(context: WorkflowContext) -> AgentExecution:
        demo_payload = parse_demo_handoff(context.handoff_context)
        if demo_payload is not None and demo_payload.stage == PROTOTYPE_BRIEF_STAGE:
            return await _handle_demo_prototype_brief(
                context,
                brief=demo_payload.artifact,
                model=model,
                openai_api_key=openai_api_key,
            )

        content = await run_deep_agent(
            role=AgentRole.PRODUCT_DESIGNER,
            agent_name=PRODUCT_DESIGNER_AGENT_NAME,
            system_prompt=PRODUCT_DESIGNER_SYSTEM_PROMPT,
            context=context,
            model=model,
            openai_api_key=openai_api_key,
            execution_context_builder=_build_execution_context,
        )
        return AgentExecution(
            messages=[
                AgentMessage(
                    agent=AgentRole.PRODUCT_DESIGNER,
                    content=content,
                )
            ]
        )

    return _handler


async def _handle_demo_prototype_brief(
    context: WorkflowContext,
    *,
    brief: str,
    model: str | BaseChatModel,
    openai_api_key: str | None,
) -> AgentExecution:
    if _find_vercel_integration(context) is None:
        return AgentExecution(
            messages=[],
            handoffs=[
                AgentHandoff(
                    source_agent=AgentRole.PRODUCT_DESIGNER,
                    target_agent=AgentRole.PRODUCT_MANAGER,
                    reason=serialize_demo_handoff(
                        stage=PROTOTYPE_SUMMARY_STAGE,
                        status=BLOCKED_STATUS,
                        artifact=(
                            "I translated the PRD into a prototype plan, but Vercel is "
                            "not connected for this server, so I could not publish the "
                            "clickable prototype. Connect Vercel and rerun the deep dive "
                            "to complete the demo flow."
                        ),
                    ),
                )
            ],
        )

    summary = await run_deep_agent(
        role=AgentRole.PRODUCT_DESIGNER,
        agent_name=PRODUCT_DESIGNER_AGENT_NAME,
        system_prompt=PRODUCT_DESIGNER_SYSTEM_PROMPT,
        context=replace(context, response_emitter=None),
        model=model,
        openai_api_key=openai_api_key,
        execution_context_builder=lambda current_context: _build_demo_execution_context(
            current_context,
            brief=brief,
        ),
    )
    return AgentExecution(
        messages=[],
        handoffs=[
            AgentHandoff(
                source_agent=AgentRole.PRODUCT_DESIGNER,
                target_agent=AgentRole.PRODUCT_MANAGER,
                reason=serialize_demo_handoff(
                    stage=PROTOTYPE_SUMMARY_STAGE,
                    artifact=summary,
                ),
            )
        ],
    )


def _build_execution_context(context: WorkflowContext) -> str:
    integrations = [
        (
            f"- {integration.provider_name} ({integration.provider_id}): "
            f"tools={', '.join(integration.tool_names) or 'none'}"
        )
        for integration in context.toolset.integrations
    ]
    if not integrations:
        integrations = ["- No connected integrations were detected."]

    return "\n".join(
        (
            "Execution context:",
            "- Use connected tools when they materially improve the design artifact.",
            "Connected integrations:",
            *integrations,
        )
    )


def _build_demo_execution_context(context: WorkflowContext, *, brief: str) -> str:
    return "\n".join(
        (
            _build_execution_context(context),
            "PM handoff PRD:",
            brief,
            (
                "Create or update a clickable Vercel prototype when possible and "
                "summarize the resulting interaction flow for the PM."
            ),
        )
    )


def _find_vercel_integration(context: WorkflowContext) -> ConnectedIntegration | None:
    for integration in context.toolset.integrations:
        if integration.provider_id == "vercel" and integration.status == "active":
            return integration
    return None


__all__ = [
    "DEFAULT_PRODUCT_DESIGNER_MODEL",
    "PRODUCT_DESIGNER_AGENT_NAME",
    "PRODUCT_DESIGNER_SYSTEM_PROMPT",
    "build_product_designer_handler",
]
