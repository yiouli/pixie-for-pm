from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from dataclasses import replace

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.tools import BaseTool

import pixie
from pixie_for_pm.agents.deep_agent import (
    DEFAULT_DEEP_AGENT_MODEL,
    build_notion_tool_guidance,
    run_deep_agent,
)
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
_VERCEL_URL_PATTERN = re.compile(
    r"https?://[^\s)>\]]*vercel\.app[^\s)>\]]*",
    re.IGNORECASE,
)


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
            messages=[],
            handoffs=[
                AgentHandoff(
                    source_agent=AgentRole.PRODUCT_DESIGNER,
                    target_agent=AgentRole.COORDINATOR,
                    reason=content,
                )
            ],
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
                    target_agent=AgentRole.COORDINATOR,
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
    deployment_result, deployment_url = await _publish_demo_prototype(
        context,
        summary=summary,
    )
    if deployment_url is None:
        blocked_artifact = pixie.wrap(
            _build_blocked_prototype_artifact(
                summary=summary,
                deployment_result=deployment_result,
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
                    target_agent=AgentRole.COORDINATOR,
                    reason=serialize_demo_handoff(
                        stage=PROTOTYPE_SUMMARY_STAGE,
                        status=BLOCKED_STATUS,
                        artifact=blocked_artifact,
                    ),
                )
            ],
        )

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
                target_agent=AgentRole.COORDINATOR,
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

    notion_guidance = (
        build_notion_tool_guidance(fetch_tool_name="notion_notion-fetch")
        if _has_notion_integration(context)
        else ()
    )
    vercel_guidance = (
        (
            "- The runtime will create a new Next.js project for this prototype "
            "build. Do not assume an existing Vercel project should be reused.",
        )
        if _find_vercel_integration(context) is not None
        else ()
    )

    return "\n".join(
        (
            "Execution context:",
            "- Use connected tools when they materially improve the design artifact.",
            *notion_guidance,
            *vercel_guidance,
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
                "Assume the runtime will create a brand new Next.js project for this "
                "prototype build instead of reusing an existing Vercel project."
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
) -> tuple[str | None, str | None]:
    project_name = _build_demo_project_name(context)
    deploy_tool = _find_deploy_tool(context)
    if deploy_tool is None:
        return None, None

    payload = _filter_tool_payload(
        deploy_tool,
        {
            "project_name": project_name,
            "deployment_summary": _deployment_summary(
                summary,
                project_name=project_name,
            ),
            "files": _build_prototype_files(summary=summary, project_name=project_name),
            "target": "production",
        },
    )
    result = await deploy_tool.ainvoke(payload)
    if isinstance(result, tuple):
        result = result[0]
    deployment_result = None if result is None else str(result)
    return deployment_result, _extract_vercel_url(deployment_result)


def _build_prototype_artifact(*, summary: str, deployment_result: str | None) -> str:
    lines = []
    if deployment_result is not None:
        lines.append(f"Deployment result: {deployment_result}")
    lines.append(summary.strip())
    return "\n\n".join(line for line in lines if line)


def _build_blocked_prototype_artifact(
    *,
    summary: str,
    deployment_result: str | None,
) -> str:
    prototype_summary = _extract_prefixed_line(summary, "Prototype summary:")
    if prototype_summary is None:
        prototype_summary = _truncate_words(_clean_text(summary), 24)

    lines = [
        (
            "I translated the PRD into a prototype plan, but I could not publish "
            "a live Vercel URL from the available runtime tool."
        )
    ]
    if deployment_result is not None:
        lines.append(f"Deployment blocker: {deployment_result}")
    lines.append(f"Prototype summary: {prototype_summary}")
    return "\n\n".join(lines)


def _deployment_summary(summary: str, *, project_name: str) -> str:
    prototype_summary = _extract_prefixed_line(summary, "Prototype summary:")
    if prototype_summary is not None:
        return (
            f"Create a new Next.js project named {project_name} for this clickable "
            f"prototype. Prototype summary: {prototype_summary}"
        )
    return (
        f"Create a new Next.js project named {project_name} for this clickable "
        f"prototype. Prototype summary: {_truncate_words(_clean_text(summary), 24)}"
    )


def _build_prototype_files(*, summary: str, project_name: str) -> dict[str, str]:
    """Build the minimal static prototype files uploaded with each Vercel deployment.

    The deployment tool requires inline file content. We render a single
    ``index.html`` that surfaces the prototype summary so reviewers landing on
    the deployment URL see the same product framing the PM received.
    """
    title = _escape_html(project_name)
    body = _escape_html(_clean_text(summary)) or _escape_html(project_name)
    html = (
        "<!doctype html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        f"<title>{title}</title>\n"
        "</head>\n"
        "<body>\n"
        f"<main><h1>{title}</h1><p>{body}</p></main>\n"
        "</body>\n"
        "</html>\n"
    )
    return {"index.html": html}


def _escape_html(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _build_demo_project_name(context: WorkflowContext) -> str:
    return _pick_project_name(context.thread_key)


def _pick_project_name(name_seed: str | None) -> str:
    if not name_seed:
        return "pixie-retention-demo"

    slug = re.sub(r"[^a-z0-9]+", "-", name_seed.casefold()).strip("-")
    if not slug:
        return "pixie-retention-demo"
    if slug.startswith("pixie-retention-demo"):
        return slug
    return f"pixie-retention-demo-{slug}"


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


def _find_deploy_tool(context: WorkflowContext) -> BaseTool | None:
    for tool_name in ("vercel_create_deployment", "vercel_deploy_to_vercel"):
        tool = _find_tool(context, tool_name)
        if tool is not None:
            return tool

    for tool in context.toolset.tools:
        lowered = tool.name.casefold()
        if "vercel" in lowered and "deploy" in lowered:
            return tool
    return None


def _filter_tool_payload(
    tool: BaseTool,
    payload: dict[str, object],
) -> dict[str, object]:
    args_schema = tool.args_schema
    if args_schema is None or isinstance(args_schema, dict):
        return payload

    field_names = set(args_schema.model_fields)
    if not field_names:
        return {}
    return {key: value for key, value in payload.items() if key in field_names}


def _extract_vercel_url(result: str | None) -> str | None:
    if result is None:
        return None
    match = _VERCEL_URL_PATTERN.search(result)
    if match is None:
        return None
    return match.group(0)


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


def _has_notion_integration(context: WorkflowContext) -> bool:
    for integration in context.toolset.integrations:
        if integration.provider_id == "notion" and integration.status == "active":
            return True
    return False


__all__ = [
    "DEFAULT_PRODUCT_DESIGNER_MODEL",
    "PRODUCT_DESIGNER_AGENT_NAME",
    "PRODUCT_DESIGNER_SYSTEM_PROMPT",
    "build_product_designer_handler",
]
