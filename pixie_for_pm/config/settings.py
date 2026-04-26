from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from pixie_for_pm.domain.models import AgentRole


@dataclass(frozen=True)
class AgentPersonaConfig:
    display_name: str
    mention_tokens: tuple[str, ...]
    webhook_url: str | None


@dataclass(frozen=True)
class AppSettings:
    discord_bot_token: str
    discord_guild_id: int
    discord_orchestration_channel_id: int
    langgraph_checkpoint_path: Path
    personas: dict[AgentRole, AgentPersonaConfig]


DEFAULT_PERSONAS: Final[dict[AgentRole, tuple[str, tuple[str, ...]]]] = {
    AgentRole.PRODUCT_MANAGER: ("Pixie PM", ("@pm", "@product-manager")),
    AgentRole.MARKET_ANALYST: (
        "Pixie Market Analyst",
        ("@market", "@market-analyst"),
    ),
    AgentRole.USER_RESEARCHER: (
        "Pixie User Researcher",
        ("@uxr", "@user-researcher"),
    ),
    AgentRole.DATA_SCIENTIST: (
        "Pixie Data Scientist",
        ("@data", "@data-scientist"),
    ),
    AgentRole.PRODUCT_DESIGNER: (
        "Pixie Product Designer",
        ("@design", "@product-designer"),
    ),
}


def _require(env: dict[str, str], key: str) -> str:
    value = env.get(key)
    if value is None or value.strip() == "":
        raise ValueError(f"Missing required environment variable: {key}")
    return value


def _parse_tokens(raw_value: str) -> tuple[str, ...]:
    tokens = tuple(token.strip() for token in raw_value.split(",") if token.strip())
    if not tokens:
        raise ValueError("Mention token configuration must include at least one token.")
    return tokens


def _load_persona(env: dict[str, str], role: AgentRole) -> AgentPersonaConfig:
    default_name, default_tokens = DEFAULT_PERSONAS[role]
    env_prefix = f"DISCORD_{role.name}"
    display_name = env.get(f"{env_prefix}_DISPLAY_NAME", default_name)
    mention_tokens = _parse_tokens(
        env.get(f"{env_prefix}_MENTION_TOKENS", ",".join(default_tokens))
    )
    webhook_url = env.get(f"{env_prefix}_WEBHOOK_URL") or None
    return AgentPersonaConfig(
        display_name=display_name,
        mention_tokens=mention_tokens,
        webhook_url=webhook_url,
    )


def load_settings(env: dict[str, str] | None = None) -> AppSettings:
    source_env = dict(os.environ if env is None else env)
    personas = {role: _load_persona(source_env, role) for role in AgentRole}
    return AppSettings(
        discord_bot_token=_require(source_env, "DISCORD_BOT_TOKEN"),
        discord_guild_id=int(_require(source_env, "DISCORD_GUILD_ID")),
        discord_orchestration_channel_id=int(
            _require(source_env, "DISCORD_ORCHESTRATION_CHANNEL_ID")
        ),
        langgraph_checkpoint_path=Path(
            source_env.get("LANGGRAPH_CHECKPOINT_PATH", ".state/pixie-langgraph.sqlite")
        ),
        personas=personas,
    )
