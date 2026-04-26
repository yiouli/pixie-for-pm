from pathlib import Path

import pytest

from pixie_for_pm.config.settings import load_settings
from pixie_for_pm.domain.models import AgentRole


def test_load_settings_builds_personas_from_environment() -> None:
    settings = load_settings(
        {
            "DISCORD_BOT_TOKEN": "discord-token",
            "DISCORD_GUILD_ID": "123",
            "DISCORD_ORCHESTRATION_CHANNEL_ID": "456",
            "LANGGRAPH_CHECKPOINT_PATH": ".state/pixie.sqlite",
            "WEB_APP_URL": "https://app.pixie.test",
            "DISCORD_MARKET_ANALYST_MENTION_TOKENS": "@market-analyst,<@&42>",
            "DISCORD_MARKET_ANALYST_WEBHOOK_URL": "https://discord.com/api/webhooks/test",
        }
    )

    assert settings.discord_guild_id == 123
    assert settings.discord_orchestration_channel_id == 456
    assert settings.langgraph_checkpoint_path == Path(".state/pixie.sqlite")
    assert settings.web_app_url == "https://app.pixie.test"
    assert settings.personas[AgentRole.MARKET_ANALYST].mention_tokens == (
        "@market-analyst",
        "<@&42>",
    )
    assert (
        settings.personas[AgentRole.MARKET_ANALYST].webhook_url
        == "https://discord.com/api/webhooks/test"
    )


def test_load_settings_supports_web_server_configuration() -> None:
    settings = load_settings(
        {
            "DISCORD_BOT_TOKEN": "discord-token",
            "DISCORD_GUILD_ID": "123",
            "DISCORD_ORCHESTRATION_CHANNEL_ID": "456",
            "WEB_APP_URL": "https://app.pixie.test",
            "DISCORD_OAUTH_CLIENT_ID": "discord-client-id",
            "DISCORD_OAUTH_CLIENT_SECRET": "discord-client-secret",
            "DISCORD_OAUTH_CALLBACK_URL": "https://api.pixie.test/api/auth/discord/callback",
            "SESSION_SECRET_KEY": "session-secret",
            "SUPABASE_URL": "https://supabase.pixie.test",
            "SUPABASE_SERVICE_ROLE_KEY": "service-role",
            "CREDENTIALS_ENCRYPTION_KEY": "fernet-key",
            "OAUTH_CALLBACK_URL": "https://api.pixie.test/api/connections/oauth/callback",
            "NOTION_CLIENT_ID": "notion-id",
            "NOTION_CLIENT_SECRET": "notion-secret",
            "GITHUB_CLIENT_ID": "github-id",
            "GITHUB_CLIENT_SECRET": "github-secret",
            "VERCEL_CLIENT_ID": "vercel-id",
            "VERCEL_CLIENT_SECRET": "vercel-secret",
            "AIRTABLE_CLIENT_ID": "airtable-id",
            "AIRTABLE_CLIENT_SECRET": "airtable-secret",
        }
    )

    assert settings.discord_oauth_client_id == "discord-client-id"
    assert settings.discord_oauth_client_secret == "discord-client-secret"
    assert settings.discord_oauth_callback_url == (
        "https://api.pixie.test/api/auth/discord/callback"
    )
    assert settings.session_secret_key == "session-secret"
    assert settings.supabase_url == "https://supabase.pixie.test"
    assert settings.supabase_service_role_key == "service-role"
    assert settings.credentials_encryption_key == "fernet-key"
    assert settings.oauth_callback_url == (
        "https://api.pixie.test/api/connections/oauth/callback"
    )
    assert settings.oauth_client_ids["notion"] == "notion-id"
    assert settings.oauth_client_ids["github"] == "github-id"
    assert settings.oauth_client_ids["vercel"] == "vercel-id"
    assert settings.oauth_client_ids["airtable"] == "airtable-id"
    assert settings.oauth_client_secrets["notion"] == "notion-secret"
    assert settings.oauth_client_secrets["github"] == "github-secret"
    assert settings.oauth_client_secrets["vercel"] == "vercel-secret"
    assert settings.oauth_client_secrets["airtable"] == "airtable-secret"


def test_load_settings_prefers_local_dotenv_over_stale_shell_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text(
        "\n".join(
            [
                "DISCORD_BOT_TOKEN=discord-token",
                "DISCORD_GUILD_ID=123",
                "DISCORD_ORCHESTRATION_CHANNEL_ID=456",
                "WEB_APP_URL=http://localhost:8000",
                "DISCORD_OAUTH_CALLBACK_URL=http://localhost:8000/api/auth/discord/callback",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("WEB_APP_URL", "http://localhost:5173")
    monkeypatch.setenv(
        "DISCORD_OAUTH_CALLBACK_URL",
        "http://localhost:5173/api/auth/discord/callback",
    )

    settings = load_settings()

    assert settings.web_app_url == "http://localhost:8000"
    assert settings.discord_oauth_callback_url == (
        "http://localhost:8000/api/auth/discord/callback"
    )
