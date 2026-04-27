from __future__ import annotations

from collections.abc import Awaitable, Callable

from langchain_core.language_models.chat_models import BaseChatModel

from pixie_for_pm.agents.deep_agent import (
    DEFAULT_DEEP_AGENT_MODEL,
    build_deep_agent_handler,
)
from pixie_for_pm.domain.models import (
    AgentExecution,
    AgentMessage,
    AgentRole,
    WorkflowContext,
)
from pixie_for_pm.integrations.toolset import ConnectedIntegration

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
    return build_deep_agent_handler(
        role=AgentRole.USER_RESEARCHER,
        agent_name=USER_RESEARCHER_AGENT_NAME,
        system_prompt=_SYSTEM_PROMPT,
        model=model,
        openai_api_key=openai_api_key,
        execution_context_builder=_build_execution_context,
        preflight_check=_require_notion_integration,
    )


def _require_notion_integration(context: WorkflowContext) -> AgentExecution | None:
    notion_integration = _find_notion_integration(context)
    if notion_integration is not None and notion_integration.tool_names:
        return None

    return AgentExecution(
        messages=[
            AgentMessage(
                agent=AgentRole.USER_RESEARCHER,
                content=(
                    "Connect Notion for this server before running the user researcher. "
                    "This workflow reads product context, methodology, interview "
                    "materials, and prior learnings from Notion, then writes tagging "
                    "artifacts and the final synthesis back there."
                ),
            )
        ]
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
            "Connected integrations:",
            integrations,
        )
    )


def _find_notion_integration(context: WorkflowContext) -> ConnectedIntegration | None:
    for integration in context.toolset.integrations:
        if integration.provider_id == "notion" and integration.status == "active":
            return integration
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
