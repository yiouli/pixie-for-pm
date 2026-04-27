from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from pixie_for_pm.agents.demo_flow import (
    BLOCKED_STATUS,
    OPTIONS_SUMMARY_STAGE,
    PRD_BRIEF_STAGE,
    PRD_READY_STAGE,
    PROTOTYPE_BRIEF_STAGE,
    PROTOTYPE_SUMMARY_STAGE,
    RESEARCH_BRIEF_STAGE,
    RESEARCH_FINDINGS_STAGE,
    is_retention_next_step_demo,
    parse_bare_option_choice,
    parse_deep_dive_option,
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


@dataclass(frozen=True)
class DispatchDecision:
    target_agent: AgentRole | None
    reason: str
    response: str | None = None


def build_coordinator_handler() -> (
    Callable[[WorkflowContext], Awaitable[AgentExecution]]
):
    async def _handler(context: WorkflowContext) -> AgentExecution:
        demo_payload = parse_demo_handoff(context.handoff_context)
        if demo_payload is not None:
            demo_execution = _handle_demo_handoff(context, demo_payload)
            if demo_execution is not None:
                return demo_execution

        if (
            context.handoff_context is not None
            and context.handoff_context.strip() != ""
        ):
            return AgentExecution(
                messages=[
                    AgentMessage(
                        agent=AgentRole.COORDINATOR,
                        content=context.handoff_context.strip(),
                    )
                ]
            )

        recent_reply = _extract_recent_coordinator_reply(context)
        if is_retention_next_step_demo(context.user_message):
            return AgentExecution(
                messages=[
                    AgentMessage(
                        agent=AgentRole.COORDINATOR,
                        content="let me look into the user interviews and get back to you.",
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
            return AgentExecution(
                messages=[
                    AgentMessage(
                        agent=AgentRole.COORDINATOR,
                        content="sure. let me do that",
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
            return AgentExecution(
                messages=[
                    AgentMessage(
                        agent=AgentRole.COORDINATOR,
                        content="on it.",
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
            return AgentExecution(
                messages=[
                    AgentMessage(
                        agent=AgentRole.COORDINATOR,
                        content=decision.response
                        or "I can only help with product management work.",
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


def _handle_demo_handoff(
    context: WorkflowContext,
    payload: object,
) -> AgentExecution | None:
    del payload
    demo_payload = parse_demo_handoff(context.handoff_context)
    if demo_payload is None:
        return None

    if demo_payload.stage == RESEARCH_FINDINGS_STAGE:
        if demo_payload.status == BLOCKED_STATUS:
            return AgentExecution(
                messages=[
                    AgentMessage(
                        agent=AgentRole.COORDINATOR,
                        content=demo_payload.artifact,
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

    if demo_payload.stage in {OPTIONS_SUMMARY_STAGE, PRD_READY_STAGE}:
        return AgentExecution(
            messages=[
                AgentMessage(
                    agent=AgentRole.COORDINATOR,
                    content=demo_payload.artifact,
                )
            ]
        )

    if demo_payload.stage == PROTOTYPE_SUMMARY_STAGE:
        return AgentExecution(
            messages=[
                AgentMessage(
                    agent=AgentRole.COORDINATOR,
                    content=_build_prototype_reply(demo_payload.artifact),
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
        prototype_summary = "The concept turns the selected retention idea into a lighter weekly prep loop."

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


def build_dispatcher_handler() -> (
    Callable[[WorkflowContext], Awaitable[AgentExecution]]
):
    return build_coordinator_handler()


__all__ = [
    "DispatchDecision",
    "build_coordinator_handler",
    "build_dispatcher_handler",
    "decide_dispatch",
]
