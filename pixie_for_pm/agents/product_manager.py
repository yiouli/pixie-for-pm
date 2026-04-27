from __future__ import annotations

from collections.abc import Awaitable, Callable

from langchain_core.language_models.chat_models import BaseChatModel

from pixie_for_pm.agents.deep_agent import DEFAULT_DEEP_AGENT_MODEL, run_deep_agent
from pixie_for_pm.agents.demo_flow import (
    BLOCKED_STATUS,
    PROTOTYPE_BRIEF_STAGE,
    PROTOTYPE_SUMMARY_STAGE,
    RESEARCH_BRIEF_STAGE,
    RESEARCH_FINDINGS_STAGE,
    is_retention_next_step_demo,
    parse_deep_dive_option,
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

DEFAULT_PRODUCT_MANAGER_MODEL = DEFAULT_DEEP_AGENT_MODEL
PRODUCT_MANAGER_AGENT_NAME = "pixie_product_manager"

PRODUCT_MANAGER_SYSTEM_PROMPT = """
You are Pixie's product manager agent.

Respond like a senior PM working inside a cross-functional product team.
Be concrete, concise, and execution-oriented.
Use any connected tools when they materially improve the answer.
When you reference prior internal context, synthesize it instead of repeating it verbatim.

When the work requires a PRD, write a Lenny Rachitsky-style PRD.
Spell the structure out explicitly with:
- title and one-sentence product thesis
- problem statement
- why now
- target user and core job to be done
- key insights and evidence
- goals and non-goals
- hypotheses
- solution overview
- MVP scope
- user experience notes
- success metrics
- launch and iteration plan
- risks and open questions

For the retention-next-step demo workflow:
- if the user says retention is low and asks what to build next,
  delegate to the user researcher first
- after the researcher returns, synthesize exactly three distinct hypotheses,
    include a high-level proposal for each, and ask which option to deepen
- if the user asks to go deeper on a numbered option, draft the PRD
    internally first, then hand it to the product designer for a clickable
    Vercel prototype, then return with a concise review-ready summary
    for the user
""".strip()


def build_product_manager_handler(
    *,
    model: str | BaseChatModel = DEFAULT_PRODUCT_MANAGER_MODEL,
    openai_api_key: str | None = None,
) -> Callable[[WorkflowContext], Awaitable[AgentExecution]]:
    async def _handler(context: WorkflowContext) -> AgentExecution:
        demo_payload = parse_demo_handoff(context.handoff_context)
        if demo_payload is not None:
            if demo_payload.stage == RESEARCH_FINDINGS_STAGE:
                return await _respond_to_research_findings(
                    context,
                    findings=demo_payload.artifact,
                    status=demo_payload.status,
                    model=model,
                    openai_api_key=openai_api_key,
                )
            if demo_payload.stage == PROTOTYPE_SUMMARY_STAGE:
                return await _respond_to_prototype_summary(
                    context,
                    summary=demo_payload.artifact,
                    status=demo_payload.status,
                    model=model,
                    openai_api_key=openai_api_key,
                )

        if is_retention_next_step_demo(context.user_message):
            return AgentExecution(
                messages=[],
                handoffs=[
                    AgentHandoff(
                        source_agent=AgentRole.PRODUCT_MANAGER,
                        target_agent=AgentRole.USER_RESEARCHER,
                        reason=serialize_demo_handoff(
                            stage=RESEARCH_BRIEF_STAGE,
                            artifact=_build_research_brief(context),
                        ),
                    )
                ],
            )

        deep_dive_option = parse_deep_dive_option(context.user_message)
        if deep_dive_option is not None:
            prd = await run_deep_agent(
                role=AgentRole.PRODUCT_MANAGER,
                agent_name=PRODUCT_MANAGER_AGENT_NAME,
                system_prompt=PRODUCT_MANAGER_SYSTEM_PROMPT,
                context=context,
                model=model,
                openai_api_key=openai_api_key,
                execution_context_builder=lambda current_context: _build_prd_context(
                    current_context,
                    option_number=deep_dive_option,
                ),
            )
            return AgentExecution(
                messages=[],
                handoffs=[
                    AgentHandoff(
                        source_agent=AgentRole.PRODUCT_MANAGER,
                        target_agent=AgentRole.PRODUCT_DESIGNER,
                        reason=serialize_demo_handoff(
                            stage=PROTOTYPE_BRIEF_STAGE,
                            artifact=prd,
                        ),
                    )
                ],
            )

        content = await run_deep_agent(
            role=AgentRole.PRODUCT_MANAGER,
            agent_name=PRODUCT_MANAGER_AGENT_NAME,
            system_prompt=PRODUCT_MANAGER_SYSTEM_PROMPT,
            context=context,
            model=model,
            openai_api_key=openai_api_key,
            execution_context_builder=_build_default_execution_context,
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


async def _respond_to_research_findings(
    context: WorkflowContext,
    *,
    findings: str,
    status: str,
    model: str | BaseChatModel,
    openai_api_key: str | None,
) -> AgentExecution:
    if status == BLOCKED_STATUS:
        return AgentExecution(
            messages=[
                AgentMessage(
                    agent=AgentRole.PRODUCT_MANAGER,
                    content=findings,
                )
            ]
        )

    content = await run_deep_agent(
        role=AgentRole.PRODUCT_MANAGER,
        agent_name=PRODUCT_MANAGER_AGENT_NAME,
        system_prompt=PRODUCT_MANAGER_SYSTEM_PROMPT,
        context=context,
        model=model,
        openai_api_key=openai_api_key,
        execution_context_builder=lambda current_context: _build_hypothesis_context(
            current_context,
            findings=findings,
        ),
    )
    return AgentExecution(
        messages=[
            AgentMessage(
                agent=AgentRole.PRODUCT_MANAGER,
                content=content,
            )
        ]
    )


async def _respond_to_prototype_summary(
    context: WorkflowContext,
    *,
    summary: str,
    status: str,
    model: str | BaseChatModel,
    openai_api_key: str | None,
) -> AgentExecution:
    if status == BLOCKED_STATUS:
        return AgentExecution(
            messages=[
                AgentMessage(
                    agent=AgentRole.PRODUCT_MANAGER,
                    content=summary,
                )
            ]
        )

    content = await run_deep_agent(
        role=AgentRole.PRODUCT_MANAGER,
        agent_name=PRODUCT_MANAGER_AGENT_NAME,
        system_prompt=PRODUCT_MANAGER_SYSTEM_PROMPT,
        context=context,
        model=model,
        openai_api_key=openai_api_key,
        execution_context_builder=lambda current_context: _build_prototype_review_context(
            current_context,
            summary=summary,
        ),
    )
    return AgentExecution(
        messages=[
            AgentMessage(
                agent=AgentRole.PRODUCT_MANAGER,
                content=content,
            )
        ]
    )


def _build_default_execution_context(context: WorkflowContext) -> str:
    return "\n".join(
        (
            "Execution context:",
            "- Work like the PM lead for a cross-functional product squad.",
            "- Use connected tools when they materially improve confidence or speed.",
            "Connected integrations:",
            _describe_integrations(context),
        )
    )


def _build_research_brief(context: WorkflowContext) -> str:
    return "\n".join(
        (
            "Retention demo brief:",
            f"- User request: {context.user_message}",
            (
                "- Identify why retention is low, what repeat-use barrier matters "
                "most, and what behavior change seems most promising."
            ),
            (
                "- Return the smallest defensible synthesis the PM can use "
                "to propose three next-build hypotheses."
            ),
        )
    )


def _build_hypothesis_context(context: WorkflowContext, *, findings: str) -> str:
    return "\n".join(
        (
            _build_default_execution_context(context),
            "Retention demo instructions:",
            "- The user researcher already completed the insight pass.",
            "- Use the research findings below to propose exactly three hypotheses.",
            (
                "- For each hypothesis, include the idea, why it should "
                "improve retention, and a high-level proposal."
            ),
            "- End by asking the user which option to deepen next.",
            "Research findings:",
            findings,
        )
    )


def _build_prd_context(context: WorkflowContext, *, option_number: int) -> str:
    return "\n".join(
        (
            _build_default_execution_context(context),
            "Retention demo instructions:",
            (
                f"- The user asked to go deeper on option #{option_number} "
                "from the prior PM response."
            ),
            (
                "- Draft the PRD internally using the Lenny Rachitsky-style "
                "structure from the system prompt."
            ),
            (
                "- Be specific enough that a product designer can turn it "
                "into a clickable Vercel prototype."
            ),
            "- Do not ask the user follow-up questions in this artifact.",
        )
    )


def _build_prototype_review_context(context: WorkflowContext, *, summary: str) -> str:
    return "\n".join(
        (
            _build_default_execution_context(context),
            "Retention demo instructions:",
            "- The designer has already translated the PRD into a clickable prototype.",
            "- Summarize the PRD and prototype together for the user.",
            (
                "- Call out what was designed, what behavior change it targets, "
                "and what feedback you want from the user before delivery."
            ),
            "Designer handback:",
            summary,
        )
    )


def _describe_integrations(context: WorkflowContext) -> str:
    integrations = [
        (
            f"- {integration.provider_name} ({integration.provider_id}): "
            f"tools={', '.join(integration.tool_names) or 'none'}"
        )
        for integration in context.toolset.integrations
    ]
    if not integrations:
        return "- No connected integrations were detected."
    return "\n".join(integrations)


__all__ = [
    "DEFAULT_PRODUCT_MANAGER_MODEL",
    "PRODUCT_MANAGER_AGENT_NAME",
    "PRODUCT_MANAGER_SYSTEM_PROMPT",
    "build_product_manager_handler",
]
