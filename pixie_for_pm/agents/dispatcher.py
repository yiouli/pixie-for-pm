from __future__ import annotations

import json
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from langchain_core.language_models.chat_models import BaseChatModel

from pixie_for_pm.agents.deep_agent import DEFAULT_DEEP_AGENT_MODEL, run_deep_agent
from pixie_for_pm.agents.demo_flow import (
    BLOCKED_STATUS,
    OPTIONS_SUMMARY_ARTIFACT_KIND,
    OPTIONS_SUMMARY_STAGE,
    PRD_BRIEF_STAGE,
    PRD_READY_ARTIFACT_KIND,
    PRD_READY_STAGE,
    PROTOTYPE_BRIEF_STAGE,
    PROTOTYPE_SUMMARY_STAGE,
    RESEARCH_BRIEF_STAGE,
    RESEARCH_FINDINGS_STAGE,
    is_retention_next_step_demo,
    parse_bare_option_choice,
    parse_deep_dive_option,
    parse_demo_artifact,
    parse_demo_handoff,
    parse_prd_request_option,
    parse_prototype_approval,
    serialize_demo_handoff,
)
from pixie_for_pm.domain.models import (
    AgentExecution,
    AgentHandoff,
    AgentMessage,
    AgentRole,
    WorkflowContext,
)
from pixie_for_pm.integrations.toolset import AgentToolset

_MARKET_ANALYST_KEYWORDS = (
    "tam",
    "sam",
    "som",
    "market",
    "competitive",
    "competition",
    "competitor",
    "segment",
    "pricing",
    "positioning",
    "landscape",
    "go to market",
    "gtm",
)

_USER_RESEARCHER_KEYWORDS = (
    "interview",
    "survey",
    "usability",
    "persona",
    "feedback",
    "research",
    "diary study",
    "customer call",
    "user test",
    "jobs to be done",
    "jtbd",
)

_PRODUCT_DESIGNER_KEYWORDS = (
    "wireframe",
    "mockup",
    "prototype",
    "design",
    "ui",
    "ux",
    "layout",
    "flow",
    "journey",
    "screen",
    "visual",
)

_PRODUCT_CONTEXT_KEYWORDS = (
    "product",
    "feature",
    "roadmap",
    "mvp",
    "launch",
    "onboarding",
    "retention",
    "activation",
    "funnel",
    "metric",
    "analytics",
    "experiment",
    "hypothesis",
    "backlog",
    "strategy",
    "priorit",
    "requirement",
    "prd",
    "spec",
    "user",
    "customer",
    "market",
    "design",
    "research",
)

_IRRELEVANT_KEYWORDS = (
    "recipe",
    "poem",
    "joke",
    "horoscope",
    "weather",
    "sports score",
    "movie review",
    "travel itinerary",
    "pancake",
    "homework",
)

_URL_PATTERN = re.compile(r"https?://\S+")

DEFAULT_COORDINATOR_MODEL = DEFAULT_DEEP_AGENT_MODEL
COORDINATOR_AGENT_NAME = "pixie_coordinator"

COORDINATOR_SYSTEM_PROMPT = """
You are Pixie's coordinator agent.

You are the only agent that speaks to the user in Discord.
Turn internal specialist artifacts and workflow state into concise, natural,
user-facing replies.
Do not mention internal agents, handoffs, prompts, or hidden workflow state.
Do not use canned filler or jokey phrasing.
Keep replies brief, clear, and action-oriented.
When you ask the user to choose, make the next action explicit.
When you share a link, include it inline.
""".strip()


@dataclass(frozen=True)
class DispatchDecision:
    target_agent: AgentRole | None
    reason: str
    response: str | None = None


def build_coordinator_handler(
    *,
    model: str | BaseChatModel = DEFAULT_COORDINATOR_MODEL,
    openai_api_key: str | None = None,
) -> Callable[[WorkflowContext], Awaitable[AgentExecution]]:
    async def _handler(context: WorkflowContext) -> AgentExecution:
        demo_payload = parse_demo_handoff(context.handoff_context)
        if demo_payload is not None:
            demo_execution = await _handle_demo_handoff(
                context,
                demo_payload,
                model=model,
                openai_api_key=openai_api_key,
            )
            if demo_execution is not None:
                return demo_execution

        if (
            context.handoff_context is not None
            and context.handoff_context.strip() != ""
        ):
            reply = await _generate_coordinator_reply(
                context,
                model=model,
                openai_api_key=openai_api_key,
                execution_context_builder=lambda current_context: (
                    _build_generic_handoff_reply_context(
                        current_context,
                        artifact=context.handoff_context or "",
                    )
                ),
            )
            return AgentExecution(
                messages=[
                    AgentMessage(
                        agent=AgentRole.COORDINATOR,
                        content=reply,
                    )
                ]
            )

        recent_reply = _extract_recent_coordinator_reply(context)
        if is_retention_next_step_demo(context.user_message):
            kickoff = await _generate_coordinator_reply(
                context,
                model=model,
                openai_api_key=openai_api_key,
                execution_context_builder=_build_retention_kickoff_context,
                stream_to_user=False,
            )
            return AgentExecution(
                messages=[
                    AgentMessage(
                        agent=AgentRole.COORDINATOR,
                        content=kickoff,
                    )
                ],
                handoffs=[
                    AgentHandoff(
                        source_agent=AgentRole.COORDINATOR,
                        target_agent=AgentRole.USER_RESEARCHER,
                        reason=serialize_demo_handoff(
                            stage=RESEARCH_BRIEF_STAGE,
                            artifact=_build_research_brief(context),
                        ),
                    )
                ],
            )

        prd_option = parse_prd_request_option(
            context.user_message,
            recent_reply=recent_reply,
        )
        if prd_option is None:
            prd_option = parse_deep_dive_option(context.user_message)
        if prd_option is None:
            prd_option = parse_bare_option_choice(
                context.user_message,
                recent_pm_reply=recent_reply,
            )
        if prd_option is not None:
            kickoff = await _generate_coordinator_reply(
                context,
                model=model,
                openai_api_key=openai_api_key,
                execution_context_builder=lambda current_context: _build_prd_kickoff_context(
                    current_context,
                    option_number=prd_option,
                    recent_reply=recent_reply,
                ),
                stream_to_user=False,
            )
            return AgentExecution(
                messages=[
                    AgentMessage(
                        agent=AgentRole.COORDINATOR,
                        content=kickoff,
                    )
                ],
                handoffs=[
                    AgentHandoff(
                        source_agent=AgentRole.COORDINATOR,
                        target_agent=AgentRole.PRODUCT_MANAGER,
                        reason=serialize_demo_handoff(
                            stage=PRD_BRIEF_STAGE,
                            artifact=_build_prd_brief(
                                context,
                                option_number=prd_option,
                                recent_reply=recent_reply,
                            ),
                        ),
                    )
                ],
            )

        if parse_prototype_approval(
            context.user_message,
            recent_pm_reply=recent_reply,
        ):
            kickoff = await _generate_coordinator_reply(
                context,
                model=model,
                openai_api_key=openai_api_key,
                execution_context_builder=lambda current_context: _build_prototype_kickoff_context(
                    current_context,
                    recent_reply=recent_reply,
                ),
                stream_to_user=False,
            )
            return AgentExecution(
                messages=[
                    AgentMessage(
                        agent=AgentRole.COORDINATOR,
                        content=kickoff,
                    )
                ],
                handoffs=[
                    AgentHandoff(
                        source_agent=AgentRole.COORDINATOR,
                        target_agent=AgentRole.PRODUCT_DESIGNER,
                        reason=serialize_demo_handoff(
                            stage=PROTOTYPE_BRIEF_STAGE,
                            artifact=_build_designer_brief(context, recent_reply),
                        ),
                    )
                ],
            )

        decision = decide_dispatch(context.user_message)
        if decision.target_agent is None:
            reply = await _generate_coordinator_reply(
                context,
                model=model,
                openai_api_key=openai_api_key,
                execution_context_builder=lambda current_context: _build_out_of_scope_context(
                    current_context,
                ),
            )
            return AgentExecution(
                messages=[
                    AgentMessage(
                        agent=AgentRole.COORDINATOR,
                        content=reply,
                    )
                ]
            )

        return AgentExecution(
            messages=[],
            handoffs=[
                AgentHandoff(
                    source_agent=AgentRole.COORDINATOR,
                    target_agent=decision.target_agent,
                    reason=decision.reason,
                )
            ],
        )

    return _handler


async def _handle_demo_handoff(
    context: WorkflowContext,
    payload: object,
    *,
    model: str | BaseChatModel,
    openai_api_key: str | None,
) -> AgentExecution | None:
    del payload
    demo_payload = parse_demo_handoff(context.handoff_context)
    if demo_payload is None:
        return None

    if demo_payload.stage == RESEARCH_FINDINGS_STAGE:
        if demo_payload.status == BLOCKED_STATUS:
            reply = await _generate_coordinator_reply(
                context,
                model=model,
                openai_api_key=openai_api_key,
                execution_context_builder=lambda current_context: _build_blocked_reply_context(
                    current_context,
                    artifact=demo_payload.artifact,
                ),
            )
            return AgentExecution(
                messages=[
                    AgentMessage(
                        agent=AgentRole.COORDINATOR,
                        content=reply,
                    )
                ]
            )
        return AgentExecution(
            messages=[],
            handoffs=[
                AgentHandoff(
                    source_agent=AgentRole.COORDINATOR,
                    target_agent=AgentRole.PRODUCT_MANAGER,
                    reason=context.handoff_context or "",
                )
            ],
        )

    if demo_payload.stage == PRD_READY_STAGE:
        reply = _render_prd_ready_reply(demo_payload.artifact)
        return AgentExecution(
            messages=[
                AgentMessage(
                    agent=AgentRole.COORDINATOR,
                    content=reply,
                )
            ]
        )

    if demo_payload.stage == OPTIONS_SUMMARY_STAGE:
        reply = await _generate_coordinator_reply(
            context,
            model=model,
            openai_api_key=openai_api_key,
            execution_context_builder=lambda current_context: _build_demo_success_reply_context(
                current_context,
                stage=demo_payload.stage,
                artifact=demo_payload.artifact,
            ),
        )
        return AgentExecution(
            messages=[
                AgentMessage(
                    agent=AgentRole.COORDINATOR,
                    content=reply,
                )
            ]
        )

    if demo_payload.stage == PROTOTYPE_SUMMARY_STAGE:
        if demo_payload.status == BLOCKED_STATUS:
            reply = await _generate_coordinator_reply(
                context,
                model=model,
                openai_api_key=openai_api_key,
                execution_context_builder=lambda current_context: _build_blocked_reply_context(
                    current_context,
                    artifact=demo_payload.artifact,
                ),
            )
            return AgentExecution(
                messages=[
                    AgentMessage(
                        agent=AgentRole.COORDINATOR,
                        content=reply,
                    )
                ]
            )
        reply = await _generate_coordinator_reply(
            context,
            model=model,
            openai_api_key=openai_api_key,
            execution_context_builder=lambda current_context: _build_demo_success_reply_context(
                current_context,
                stage=demo_payload.stage,
                artifact=demo_payload.artifact,
            ),
        )
        return AgentExecution(
            messages=[
                AgentMessage(
                    agent=AgentRole.COORDINATOR,
                    content=reply,
                )
            ]
        )

    return None


def _build_research_brief(context: WorkflowContext) -> str:
    return "\n".join(
        (
            "Retention demo brief:",
            f"- User request: {context.user_message}",
            (
                "- Identify why retention is low, what repeat-use barrier matters "
                "most, and what behavior change looks most promising."
            ),
            (
                "- Return the smallest defensible synthesis the PM can use to "
                "propose three next-build hypotheses."
            ),
        )
    )


def _build_prd_brief(
    context: WorkflowContext,
    *,
    option_number: int,
    recent_reply: str | None,
) -> str:
    lines = [
        f"Selected option: #{option_number}",
        f"User request: {context.user_message.strip()}",
    ]
    if recent_reply is not None:
        lines.extend(("", "Prior coordinator message:", recent_reply.strip()))
    return "\n".join(lines)


def _build_designer_brief(
    context: WorkflowContext,
    recent_reply: str | None,
) -> str:
    lines = ["The user approved building a clickable prototype based on the PRD."]
    if recent_reply is not None:
        lines.extend(("", "Prior coordinator message:", recent_reply.strip()))
    lines.extend(("", f"User context: {context.user_message.strip()}"))
    return "\n".join(lines)


async def _generate_coordinator_reply(
    context: WorkflowContext,
    *,
    model: str | BaseChatModel,
    openai_api_key: str | None,
    execution_context_builder: Callable[[WorkflowContext], str],
    stream_to_user: bool = True,
) -> str:
    return await run_deep_agent(
        role=AgentRole.COORDINATOR,
        agent_name=COORDINATOR_AGENT_NAME,
        system_prompt=COORDINATOR_SYSTEM_PROMPT,
        context=_coordinator_writer_context(
            context,
            stream_to_user=stream_to_user,
        ),
        model=model,
        openai_api_key=openai_api_key,
        execution_context_builder=execution_context_builder,
    )


def _coordinator_writer_context(
    context: WorkflowContext,
    *,
    stream_to_user: bool = True,
) -> WorkflowContext:
    return WorkflowContext(
        thread_key=context.thread_key,
        current_agent=context.current_agent,
        user_message=context.user_message,
        transcript=context.transcript,
        trigger=context.trigger,
        toolset=AgentToolset(),
        status_emitter=context.status_emitter,
        response_emitter=context.response_emitter if stream_to_user else None,
        public_message_emitter=context.public_message_emitter,
        handoff_context=context.handoff_context,
    )


def _build_generic_handoff_reply_context(
    context: WorkflowContext,
    *,
    artifact: str,
) -> str:
    return "\n".join(
        (
            "Coordinator reply task:",
            "- Translate the internal artifact below into the message the user should see.",
            "- Keep the substance faithful, but remove internal workflow phrasing.",
            "- Keep it concise and natural for Discord.",
            f"User message: {context.user_message.strip()}",
            "Internal artifact:",
            artifact.strip(),
        )
    )


def _build_retention_kickoff_context(context: WorkflowContext) -> str:
    return "\n".join(
        (
            "Coordinator reply task:",
            (
                "- Acknowledge the request and say you are going to review the "
                "user interviews before recommending what to build next."
            ),
            "- Keep it to one short sentence.",
            f"User message: {context.user_message.strip()}",
        )
    )


def _build_prd_kickoff_context(
    context: WorkflowContext,
    *,
    option_number: int,
    recent_reply: str | None,
) -> str:
    lines = [
        "Coordinator reply task:",
        f"- The user picked option #{option_number} for a PRD.",
        "- Acknowledge that you are drafting the PRD now.",
        "- Keep it to one short sentence.",
        f"User message: {context.user_message.strip()}",
    ]
    if recent_reply is not None:
        lines.extend(("Recent coordinator reply:", recent_reply.strip()))
    return "\n".join(lines)


def _build_prototype_kickoff_context(
    context: WorkflowContext,
    *,
    recent_reply: str | None,
) -> str:
    lines = [
        "Coordinator reply task:",
        "- The user approved creating a clickable prototype.",
        "- Acknowledge that you are starting it now.",
        "- Keep it to one short sentence.",
        f"User message: {context.user_message.strip()}",
    ]
    if recent_reply is not None:
        lines.extend(("Recent coordinator reply:", recent_reply.strip()))
    return "\n".join(lines)


def _build_out_of_scope_context(context: WorkflowContext) -> str:
    return "\n".join(
        (
            "Coordinator reply task:",
            (
                "- Politely explain that Pixie can help with product management "
                "work such as strategy, market analysis, user research, and "
                "product design."
            ),
            "- Explain that the current request is outside that scope.",
            f"User message: {context.user_message.strip()}",
        )
    )


def _build_demo_success_reply_context(
    context: WorkflowContext,
    *,
    stage: str,
    artifact: str,
) -> str:
    if stage == OPTIONS_SUMMARY_STAGE:
        return _build_options_summary_reply_context(context, artifact=artifact)
    if stage == PRD_READY_STAGE:
        return _build_prd_ready_reply_context(context, artifact=artifact)
    if stage == PROTOTYPE_SUMMARY_STAGE:
        return _build_prototype_ready_reply_context(context, artifact=artifact)
    return _build_generic_handoff_reply_context(context, artifact=artifact)


def _build_options_summary_reply_context(
    context: WorkflowContext,
    *,
    artifact: str,
) -> str:
    payload = parse_demo_artifact(artifact)
    if payload is None or payload.get("kind") != OPTIONS_SUMMARY_ARTIFACT_KIND:
        return _build_generic_handoff_reply_context(context, artifact=artifact)

    lines = [
        "Coordinator reply task:",
        "- The user asked what Pixie should build next to improve retention.",
        "- Use the PM analysis below to produce exactly three numbered option titles.",
        "- Keep each item short and concrete.",
        "- Do not include Idea/Why/Proposal blocks or internal rationale.",
        (
            "- If a research URL is provided, mention that the full interview "
            "synthesis is saved there."
        ),
        "- End by asking which option the user wants turned into a PRD next.",
        f"User message: {context.user_message.strip()}",
        "PM analysis:",
        _string_field(payload, "pm_analysis"),
    ]
    research_url = _string_field(payload, "research_url")
    if research_url != "":
        lines.extend(("Research synthesis URL:", research_url))
    findings = _string_field(payload, "research_findings")
    if findings != "":
        lines.extend(("Research findings:", findings))
    return "\n".join(lines)


def _build_prd_ready_reply_context(
    context: WorkflowContext,
    *,
    artifact: str,
) -> str:
    payload = parse_demo_artifact(artifact)
    if payload is None or payload.get("kind") != PRD_READY_ARTIFACT_KIND:
        return _build_generic_handoff_reply_context(context, artifact=artifact)

    option_number = _string_field(payload, "option_number")
    page_url = _string_field(payload, "page_url")
    persisted = _string_field(payload, "persisted")
    lines = [
        "Coordinator reply task:",
        "- Tell the user the PRD is ready.",
        "- Include the PRD link if one is available.",
        "- If no link is available, say whether it was saved to Notion or only drafted internally.",
        "- End by asking if they want a quick clickable prototype next.",
        f"User message: {context.user_message.strip()}",
        f"Selected option number: {option_number}",
        f"Persisted: {persisted}",
    ]
    if page_url != "":
        lines.extend(("PRD URL:", page_url))
    return "\n".join(lines)


def _render_prd_ready_reply(artifact: str) -> str:
    """Deterministically render the PRD-ready reply from the PM's artifact.

    The coordinator must not author this reply with an LLM: when given only the
    option number and Notion URL, the model tends to hallucinate the PRD body
    back into the chat. The product spec calls for a short, fixed reply that
    shares the link and asks about the prototype.
    """

    payload = parse_demo_artifact(artifact)
    if payload is None or payload.get("kind") != PRD_READY_ARTIFACT_KIND:
        return artifact.strip()

    option_value = payload.get("option_number")
    option_label = (
        f"option #{option_value}" if option_value is not None else "the selected option"
    )

    page_url = _string_field(payload, "page_url")
    persisted_value = payload.get("persisted")

    if page_url != "":
        prd_line = f"PRD for {option_label} ready: {page_url}"
    elif persisted_value is True:
        prd_line = f"PRD for {option_label} saved to Notion (page link not returned)."
    else:
        prd_line = (
            f"PRD for {option_label} drafted internally "
            "(Notion write was not available)."
        )

    return f"{prd_line}\nWant me to spin up a quick clickable prototype for it next?"


def _build_prototype_ready_reply_context(
    context: WorkflowContext,
    *,
    artifact: str,
) -> str:
    return "\n".join(
        (
            "Coordinator reply task:",
            "- Share the live prototype URL if one is present.",
            "- Briefly say what the prototype demonstrates.",
            "- End by asking for feedback.",
            f"User message: {context.user_message.strip()}",
            "Internal prototype artifact:",
            artifact.strip(),
        )
    )


def _build_blocked_reply_context(
    context: WorkflowContext,
    *,
    artifact: str,
) -> str:
    return "\n".join(
        (
            "Coordinator reply task:",
            "- Explain the blocker plainly and tell the user what to fix or reconnect.",
            "- Do not mention internal handoffs.",
            f"User message: {context.user_message.strip()}",
            "Internal blocker artifact:",
            artifact.strip(),
        )
    )


def _string_field(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, sort_keys=True)


def _extract_recent_coordinator_reply(context: WorkflowContext) -> str | None:
    for message in reversed(context.transcript):
        if message.agent == AgentRole.COORDINATOR and message.content.strip() != "":
            return message.content
    return None


def _build_prototype_reply(summary: str) -> str:
    url_match = _URL_PATTERN.search(summary)
    url = url_match.group(0) if url_match is not None else None

    prototype_summary: str | None = None
    for raw_line in summary.splitlines():
        line = raw_line.strip().lstrip("-* ").strip()
        if line.lower().startswith("prototype summary:"):
            prototype_summary = line[len("Prototype summary:") :].strip()
            break

    if prototype_summary is None:
        prototype_summary = (
            "The concept turns the selected retention idea into a lighter weekly "
            "prep loop."
        )

    lines = []
    if url is not None:
        lines.append(
            f"alright the prototype is like at {url}. let me know what you think"
        )
    else:
        lines.append("alright the prototype draft is ready. let me know what you think")
    lines.append(prototype_summary)
    return "\n".join(lines)


def decide_dispatch(message: str) -> DispatchDecision:
    normalized = _normalize(message)

    if _is_irrelevant_request(normalized):
        return DispatchDecision(
            target_agent=None,
            reason="request_out_of_scope",
            response=(
                "I can help with product management work such as strategy, market "
                "analysis, user research, and product design. This request looks "
                "outside that scope, so I’m not routing it to the product team."
            ),
        )

    specialist = _select_specialist(normalized)
    if specialist is not None:
        return DispatchDecision(
            target_agent=specialist,
            reason=f"coordinator_selected_{specialist.value}",
        )

    return DispatchDecision(
        target_agent=AgentRole.PRODUCT_MANAGER,
        reason="coordinator_defaulted_to_product_manager",
    )


def _normalize(message: str) -> str:
    return message.casefold().strip()


def _is_irrelevant_request(message: str) -> bool:
    has_irrelevant_keyword = any(keyword in message for keyword in _IRRELEVANT_KEYWORDS)
    if not has_irrelevant_keyword:
        return False

    return not any(keyword in message for keyword in _PRODUCT_CONTEXT_KEYWORDS)


def _select_specialist(message: str) -> AgentRole | None:
    scores = {
        AgentRole.MARKET_ANALYST: _score_keywords(message, _MARKET_ANALYST_KEYWORDS),
        AgentRole.USER_RESEARCHER: _score_keywords(message, _USER_RESEARCHER_KEYWORDS),
        AgentRole.PRODUCT_DESIGNER: _score_keywords(
            message, _PRODUCT_DESIGNER_KEYWORDS
        ),
    }

    best_role = max(scores, key=scores.__getitem__)
    if scores[best_role] == 0:
        return None

    return best_role


def _score_keywords(message: str, keywords: tuple[str, ...]) -> int:
    return sum(1 for keyword in keywords if _keyword_in_message(message, keyword))


def _keyword_in_message(message: str, keyword: str) -> bool:
    if keyword.isalpha() and len(keyword) <= 2:
        return (
            re.search(rf"(?<![a-z0-9]){re.escape(keyword)}(?![a-z0-9])", message)
            is not None
        )

    return keyword in message


def build_dispatcher_handler(
    *,
    model: str | BaseChatModel = DEFAULT_COORDINATOR_MODEL,
    openai_api_key: str | None = None,
) -> Callable[[WorkflowContext], Awaitable[AgentExecution]]:
    return build_coordinator_handler(model=model, openai_api_key=openai_api_key)


__all__ = [
    "DispatchDecision",
    "build_coordinator_handler",
    "build_dispatcher_handler",
    "decide_dispatch",
]
