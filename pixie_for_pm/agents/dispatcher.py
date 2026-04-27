from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

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


@dataclass(frozen=True)
class DispatchDecision:
    target_agent: AgentRole | None
    reason: str
    response: str | None = None


def build_dispatcher_handler() -> (
    Callable[[WorkflowContext], Awaitable[AgentExecution]]
):
    async def _handler(context: WorkflowContext) -> AgentExecution:
        decision = decide_dispatch(context.user_message)
        if decision.target_agent is None:
            return AgentExecution(
                messages=[
                    AgentMessage(
                        agent=AgentRole.DISPATCHER,
                        content=decision.response
                        or "I can only help with product management work.",
                    )
                ]
            )

        return AgentExecution(
            messages=[],
            handoffs=[
                AgentHandoff(
                    source_agent=AgentRole.DISPATCHER,
                    target_agent=decision.target_agent,
                    reason=decision.reason,
                )
            ],
        )

    return _handler


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
            reason=f"dispatcher_selected_{specialist.value}",
        )

    return DispatchDecision(
        target_agent=AgentRole.PRODUCT_MANAGER,
        reason="dispatcher_defaulted_to_product_manager",
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
    return sum(1 for keyword in keywords if keyword in message)


__all__ = ["DispatchDecision", "build_dispatcher_handler", "decide_dispatch"]
