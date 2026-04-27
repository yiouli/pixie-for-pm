from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import replace

from langchain_core.language_models.chat_models import BaseChatModel

import pixie
from pixie_for_pm.agents.deep_agent import (
    DEFAULT_DEEP_AGENT_MODEL,
    build_notion_tool_guidance,
    run_deep_agent,
)
from pixie_for_pm.agents.demo_flow import (
    BLOCKED_STATUS,
    RESEARCH_BRIEF_STAGE,
    RESEARCH_FINDINGS_STAGE,
    parse_demo_handoff,
    serialize_demo_handoff,
)
from pixie_for_pm.domain.models import (
    AgentExecution,
    AgentHandoff,
    AgentRole,
    WorkflowContext,
)
from pixie_for_pm.integrations.toolset import (
    ConnectedIntegration,
    IntegrationLoadFailure,
)

DEFAULT_USER_RESEARCHER_MODEL = DEFAULT_DEEP_AGENT_MODEL
USER_RESEARCHER_AGENT_NAME = "pixie_user_researcher"

_SYSTEM_PROMPT = """
You are Pixie's user researcher agent.

Your job is to turn raw research inputs into defensible product decisions.
Operate as a rigorous researcher embedded in a product team.

You must follow the User Interview Synthesis Handbook methodology:
- start from the research goal and relevant participant set
- gather product context and research context before synthesizing
- separate observations from insights
- code transcript evidence with concise concept-based tags
- maintain a consistent code book and identify breadth, depth, segments,
  contradictions, and say/do gaps
- cluster codes into themes before drafting insights
- rank insights by confidence and impact
- ground every recommendation in evidence from transcripts, notes, or existing learnings

Use Notion as both the source of truth and the write-back surface for this workflow.
Always read the relevant product context from Notion first, including jobs to be done,
pain points, hypotheses, target segments, and prior decisions when available.
Then read the research context from Notion, including methodology notes, interview
script, transcripts, past learnings, prior synthesis, and existing tagging structures.

When tagging or structuring findings, prefer updating existing Notion databases or
tables. If the workspace lacks a suitable structure, create the smallest clear Notion
structure needed for:
- transcript excerpts and participant identifiers
- codes and code definitions
- themes and supporting evidence
- insights with confidence, impact, contradictions, and recommended next steps

When you write the final synthesis back to Notion, include:
- the research question and scope
- ranked insights with evidence
- segments and contradictions
- open questions
- recommended next steps

Do not invent evidence. If inputs are missing or the Notion workspace does not contain
the necessary transcripts, script, or product context, say exactly what is missing and
what you could not complete.

In your final user-facing response, summarize the key findings, what you updated in
Notion, and any blockers or follow-up needed.
""".strip()


def build_user_researcher_handler(
    *,
    model: str | BaseChatModel = DEFAULT_USER_RESEARCHER_MODEL,
    openai_api_key: str | None = None,
) -> Callable[[WorkflowContext], Awaitable[AgentExecution]]:
    async def _handler(context: WorkflowContext) -> AgentExecution:
        demo_payload = parse_demo_handoff(context.handoff_context)
        if demo_payload is not None and demo_payload.stage == RESEARCH_BRIEF_STAGE:
            return await _handle_demo_research_brief(
                context,
                brief=demo_payload.artifact,
                model=model,
                openai_api_key=openai_api_key,
            )

        preflight_result = _require_notion_integration(context)
        if preflight_result is not None:
            return preflight_result

        content = await run_deep_agent(
            role=AgentRole.USER_RESEARCHER,
            agent_name=USER_RESEARCHER_AGENT_NAME,
            system_prompt=_SYSTEM_PROMPT,
            context=context,
            model=model,
            openai_api_key=openai_api_key,
            execution_context_builder=_build_execution_context,
        )
        return AgentExecution(
            messages=[],
            handoffs=[
                AgentHandoff(
                    source_agent=AgentRole.USER_RESEARCHER,
                    target_agent=AgentRole.COORDINATOR,
                    reason=content,
                )
            ],
        )

    return _handler


async def _handle_demo_research_brief(
    context: WorkflowContext,
    *,
    brief: str,
    model: str | BaseChatModel,
    openai_api_key: str | None,
) -> AgentExecution:
    if _require_notion_integration(context) is not None:
        blocked_artifact = pixie.wrap(
            (
                "I couldn't complete the retention insight pass because Notion is "
                "not connected for this server. Connect Notion and rerun the "
                "request so I can pull interview context, prior learnings, and "
                "transcript evidence."
            ),
            purpose="state",
            name="research_artifact",
            description="Internal research synthesis or blocker passed back to the PM.",
        )
        return AgentExecution(
            messages=[],
            handoffs=[
                AgentHandoff(
                    source_agent=AgentRole.USER_RESEARCHER,
                    target_agent=AgentRole.COORDINATOR,
                    reason=serialize_demo_handoff(
                        stage=RESEARCH_FINDINGS_STAGE,
                        status=BLOCKED_STATUS,
                        artifact=blocked_artifact,
                    ),
                )
            ],
        )

    findings = await run_deep_agent(
        role=AgentRole.USER_RESEARCHER,
        agent_name=USER_RESEARCHER_AGENT_NAME,
        system_prompt=_SYSTEM_PROMPT,
        context=replace(context, response_emitter=None),
        model=model,
        openai_api_key=openai_api_key,
        execution_context_builder=lambda current_context: _build_demo_execution_context(
            current_context,
            brief=brief,
        ),
    )
    findings = pixie.wrap(
        findings,
        purpose="state",
        name="research_artifact",
        description="Internal research synthesis passed from the user researcher to the PM.",
    )
    return AgentExecution(
        messages=[],
        handoffs=[
            AgentHandoff(
                source_agent=AgentRole.USER_RESEARCHER,
                target_agent=AgentRole.COORDINATOR,
                reason=serialize_demo_handoff(
                    stage=RESEARCH_FINDINGS_STAGE,
                    artifact=findings,
                ),
            )
        ],
    )


def _require_notion_integration(context: WorkflowContext) -> AgentExecution | None:
    notion_integration = _find_notion_integration(context)
    if notion_integration is not None and notion_integration.tool_names:
        return None

    notion_failure = _find_notion_failure(context)
    if notion_failure is not None:
        return AgentExecution(
            messages=[],
            handoffs=[
                AgentHandoff(
                    source_agent=AgentRole.USER_RESEARCHER,
                    target_agent=AgentRole.COORDINATOR,
                    reason=(
                        "Notion is connected for this server, but Pixie couldn't "
                        "initialize the Notion tools. The current authorization may be "
                        "invalid or expired. Reconnect Notion and try again. "
                        f"Initialization error: {notion_failure.error}"
                    ),
                )
            ],
        )

    return AgentExecution(
        messages=[],
        handoffs=[
            AgentHandoff(
                source_agent=AgentRole.USER_RESEARCHER,
                target_agent=AgentRole.COORDINATOR,
                reason=(
                    "Connect Notion for this server before running the user researcher. "
                    "This workflow reads product context, methodology, interview "
                    "materials, and prior learnings from Notion, then writes tagging "
                    "artifacts and the final synthesis back there."
                ),
            )
        ],
    )


def _build_execution_context(context: WorkflowContext) -> str:
    integrations = "\n".join(
        _describe_integration(integration)
        for integration in context.toolset.integrations
    )
    if integrations == "":
        integrations = "- No connected integrations were detected."

    return "\n".join(
        (
            "Execution context:",
            "- Notion must be used for both context retrieval and write-back.",
            (
                "- Read the product context first: JTBD, pain points, target users, "
                "hypotheses, and prior decisions."
            ),
            (
                "- Read the research context next: methodology, interview script, "
                "transcripts, tagged data, and past learnings."
            ),
            (
                "- Apply the handbook workflow: code evidence, cluster themes, identify "
                "segments and contradictions, then synthesize ranked insights."
            ),
            (
                "- Update Notion with transcript tagging and the final synthesis "
                "artifacts before concluding."
            ),
            *build_notion_tool_guidance(
                fetch_tool_name="notion_notion-fetch",
                include_write_schema_guidance=True,
            ),
            "Connected integrations:",
            integrations,
        )
    )


def _build_demo_execution_context(context: WorkflowContext, *, brief: str) -> str:
    return "\n".join(
        (
            _build_execution_context(context),
            "PM retention demo brief:",
            brief,
            (
                "Return the retention findings as a concise internal "
                "synthesis the PM can use immediately."
            ),
            (
                "If you successfully save the synthesis in Notion, end with "
                "`Notion synthesis URL: <canonical notion url>` so the PM can "
                "share it back to the user."
            ),
        )
    )


def _find_notion_integration(context: WorkflowContext) -> ConnectedIntegration | None:
    for integration in context.toolset.integrations:
        if integration.provider_id == "notion" and integration.status == "active":
            return integration
    return None


def _find_notion_failure(
    context: WorkflowContext,
) -> IntegrationLoadFailure | None:
    for failure in context.toolset.failures:
        if failure.provider_id == "notion" and failure.status == "active":
            return failure
    return None


def _describe_integration(integration: ConnectedIntegration) -> str:
    scopes = (
        ", ".join(integration.scopes) if integration.scopes else "unspecified scopes"
    )
    tools = ", ".join(integration.tool_names) if integration.tool_names else "no tools"
    return (
        f"- {integration.provider_name} ({integration.provider_id}): "
        f"status={integration.status}; scopes={scopes}; tools={tools}"
    )
