from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from dataclasses import replace

import pixie
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.tools import BaseTool

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

_URL_PATTERN = re.compile(r"https?://\S+")


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
        blocked_artifact = pixie.wrap(
            (
                "I translated the PRD into a prototype plan, but Vercel is not "
                "connected for this server, so I could not publish the clickable "
                "prototype. Connect Vercel and rerun the deep dive to complete the "
                "demo flow."
            ),
            purpose="state",
            name="prototype_artifact",
            description="Prototype summary or blocker returned from the designer to the PM.",
        )
        return AgentExecution(
            messages=[],
            handoffs=[
                AgentHandoff(
                    source_agent=AgentRole.PRODUCT_DESIGNER,
                    target_agent=AgentRole.PRODUCT_MANAGER,
                    reason=serialize_demo_handoff(
                        stage=PROTOTYPE_SUMMARY_STAGE,
                        status=BLOCKED_STATUS,
                        artifact=blocked_artifact,
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
    deployment_result = await _publish_demo_prototype(context, summary=summary)
    artifact = _build_prototype_artifact(
        summary=summary,
        deployment_result=deployment_result,
    )
    summary = pixie.wrap(
        artifact,
        purpose="state",
        name="prototype_artifact",
        description="Prototype summary returned from the designer to the PM.",
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
                "Return only the internal prototype plan for the PM. Do not claim the "
                "prototype was published; the runtime will handle the Vercel deployment."
            ),
            (
                "Use this exact structure: `Prototype summary: <one sentence>` on the "
                "first line, then sections for Core user journey, Critical screens and "
                "states, Interaction model, and Open questions."
            ),
        )
    )


async def _publish_demo_prototype(
    context: WorkflowContext, *, summary: str
) -> str | None:
    project_listing = await _invoke_text_tool(
        context,
        "vercel_list_projects",
        {"team_name": None},
    )
    project_name = _pick_project_name(project_listing)
    return await _invoke_text_tool(
        context,
        "vercel_create_deployment",
        {
            "project_name": project_name,
            "deployment_summary": _deployment_summary(summary),
        },
    )


def _build_prototype_artifact(*, summary: str, deployment_result: str | None) -> str:
    lines = []
    if deployment_result is not None:
        lines.append(f"Deployment result: {deployment_result}")
    lines.append(summary.strip())
    return "\n\n".join(line for line in lines if line)


def _deployment_summary(summary: str) -> str:
    prototype_summary = _extract_prefixed_line(summary, "Prototype summary:")
    if prototype_summary is not None:
        return prototype_summary
    return _truncate_words(_clean_text(summary), 24)


def _pick_project_name(project_listing: str | None) -> str:
    if project_listing is None:
        return "pixie-retention-demo"

    for raw_line in project_listing.splitlines():
        line = raw_line.strip().lstrip("-* ").strip()
        if line != "":
            return line.split()[0]
    return "pixie-retention-demo"


def _extract_prefixed_line(text: str, prefix: str) -> str | None:
    for raw_line in text.splitlines():
        line = raw_line.strip().lstrip("-* ").strip()
        if line.lower().startswith(prefix.lower()):
            return line[len(prefix) :].strip()
    return None


def _clean_text(text: str) -> str:
    cleaned = re.sub(r"[*_`#]", "", text)
    cleaned = _URL_PATTERN.sub("", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def _truncate_words(text: str, limit: int) -> str:
    words = text.split()
    if len(words) <= limit:
        return " ".join(words)
    return " ".join(words[:limit]).rstrip(".,;:") + "..."


def _find_tool(context: WorkflowContext, tool_name: str) -> BaseTool | None:
    for tool in context.toolset.tools:
        if tool.name == tool_name:
            return tool
    return None


async def _invoke_text_tool(
    context: WorkflowContext,
    tool_name: str,
    payload: dict[str, object],
) -> str | None:
    tool = _find_tool(context, tool_name)
    if tool is None:
        return None

    result = await tool.ainvoke(payload)
    if isinstance(result, tuple):
        return str(result[0])
    return str(result)


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
