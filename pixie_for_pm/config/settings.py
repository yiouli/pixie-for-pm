from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from pixie_for_pm.discord.install import default_install_permissions
from pixie_for_pm.domain.models import AgentRole


@dataclass(frozen=True)
class AgentPersonaConfig:
    display_name: str
    mention_tokens: tuple[str, ...]
    webhook_url: str | None


@dataclass(frozen=True)
class AppSettings:
    discord_bot_token: str
    discord_application_id: str | None
    discord_guild_id: int | None
    discord_install_permissions: int
    connection_store_sqlite_path: Path
    langgraph_checkpoint_path: Path
    web_app_url: str | None
    # Discord OAuth login (used by the settings web app's login flow)
    discord_oauth_client_id: str | None
    discord_oauth_client_secret: str | None
    discord_oauth_callback_url: str | None
    # Session cookie signing key (Fernet key, see web/session.py)
    session_secret_key: str | None
    # Supabase connection (optional; used by SupabaseConnectionStore)
    supabase_url: str | None
    supabase_service_role_key: str | None
    # Credential storage encryption key (Fernet key)
    credentials_encryption_key: str | None
    # Integration provider OAuth credentials
    oauth_callback_url: str | None
    oauth_client_ids: dict[str, str]
    oauth_client_secrets: dict[str, str]
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


def _parse_dotenv_value(raw_value: str) -> str:
    value = raw_value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def _load_local_dotenv() -> dict[str, str]:
    dotenv_path = Path.cwd() / ".env"
    if not dotenv_path.is_file():
        return {}

    values: dict[str, str] = {}
    for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line == "" or line.startswith("#") or "=" not in line:
            continue
        key, raw_value = line.split("=", 1)
        key = key.strip()
        if key == "":
            continue
        values[key] = _parse_dotenv_value(raw_value)
    return values


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


def _optional(env: dict[str, str], key: str) -> str | None:
    value = env.get(key)
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _optional_int(env: dict[str, str], key: str) -> int | None:
    value = _optional(env, key)
    if value is None:
        return None
    return int(value)


def _load_oauth_values(env: dict[str, str], suffix: str) -> dict[str, str]:
    providers = ("NOTION", "GITHUB", "VERCEL", "AIRTABLE")
    values: dict[str, str] = {}
    for provider in providers:
        value = _optional(env, f"{provider}_{suffix}")
        if value is not None:
            values[provider.lower()] = value
    return values


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
    if env is None:
        source_env = dict(os.environ)
        source_env.update(_load_local_dotenv())
    else:
        source_env = dict(env)
    personas = {role: _load_persona(source_env, role) for role in AgentRole}
    return AppSettings(
        discord_bot_token=_require(source_env, "DISCORD_BOT_TOKEN"),
        discord_application_id=(
            _optional(source_env, "DISCORD_APPLICATION_ID")
            or _optional(source_env, "DISCORD_OAUTH_CLIENT_ID")
        ),
        discord_guild_id=_optional_int(source_env, "DISCORD_GUILD_ID"),
        discord_install_permissions=(
            _optional_int(source_env, "DISCORD_INSTALL_PERMISSIONS")
            or default_install_permissions()
        ),
        connection_store_sqlite_path=Path(
            source_env.get(
                "CONNECTION_STORE_SQLITE_PATH", ".state/pixie-connection-store.sqlite"
            )
        ),
        langgraph_checkpoint_path=Path(
            source_env.get("LANGGRAPH_CHECKPOINT_PATH", ".state/pixie-langgraph.sqlite")
        ),
        web_app_url=_optional(source_env, "WEB_APP_URL"),
        discord_oauth_client_id=_optional(source_env, "DISCORD_OAUTH_CLIENT_ID"),
        discord_oauth_client_secret=_optional(
            source_env, "DISCORD_OAUTH_CLIENT_SECRET"
        ),
        discord_oauth_callback_url=_optional(source_env, "DISCORD_OAUTH_CALLBACK_URL"),
        session_secret_key=_optional(source_env, "SESSION_SECRET_KEY"),
        supabase_url=_optional(source_env, "SUPABASE_URL"),
        supabase_service_role_key=_optional(source_env, "SUPABASE_SERVICE_ROLE_KEY"),
        credentials_encryption_key=_optional(source_env, "CREDENTIALS_ENCRYPTION_KEY"),
        oauth_callback_url=_optional(source_env, "OAUTH_CALLBACK_URL"),
        oauth_client_ids=_load_oauth_values(source_env, "CLIENT_ID"),
        oauth_client_secrets=_load_oauth_values(source_env, "CLIENT_SECRET"),
        personas=personas,
    )
