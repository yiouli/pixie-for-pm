from __future__ import annotations

from collections.abc import Mapping

from pixie_for_pm.config.settings import AgentPersonaConfig
from pixie_for_pm.domain.models import AgentRole


def detect_mentioned_agents(
    content: str,
    personas: Mapping[AgentRole, AgentPersonaConfig],
) -> tuple[AgentRole, ...]:
    normalized_content = content.casefold()
    return tuple(
        role
        for role in AgentRole
        if role in personas
        and any(
            token.casefold() in normalized_content
            for token in personas[role].mention_tokens
        )
    )


def detect_reply_agent(
    author_display_name: str | None,
    personas: Mapping[AgentRole, AgentPersonaConfig],
) -> AgentRole | None:
    if author_display_name is None:
        return None

    normalized_name = author_display_name.casefold()
    for role in AgentRole:
        persona = personas.get(role)
        if persona is not None and persona.display_name.casefold() == normalized_name:
            return role
    return None
