from pathlib import Path

import pytest

from pixie_for_pm.config.settings import load_settings


def test_load_settings_uses_core_environment_values() -> None:
    settings = load_settings(
        {
            "DISCORD_BOT_TOKEN": "discord-token",
            "LANGGRAPH_CHECKPOINT_PATH": ".state/pixie.sqlite",
            "WEB_APP_URL": "https://app.pixie.test",
        }
    )

    assert settings.discord_guild_id is None
    assert settings.discord_bot_token == "discord-token"
    assert settings.langgraph_checkpoint_path == Path(".state/pixie.sqlite")
    assert settings.web_app_url == "https://app.pixie.test"
    assert settings.oauth_client_ids == {}
    assert settings.oauth_client_secrets == {}


def test_load_settings_supports_web_server_configuration() -> None:
    settings = load_settings(
        {
            "DISCORD_BOT_TOKEN": "discord-token",
            "DISCORD_APPLICATION_ID": "discord-app-id",
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

    assert settings.discord_application_id == "discord-app-id"
    assert settings.discord_oauth_client_id == "discord-client-id"
    assert settings.discord_oauth_client_secret == "discord-client-secret"
    assert settings.discord_oauth_callback_url == (
        "https://api.pixie.test/api/auth/discord/callback"
    )
    assert settings.discord_install_permissions == 309237713920
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


def test_load_settings_falls_back_to_discord_oauth_client_id_for_install_app_id() -> (
    None
):
    settings = load_settings(
        {
            "DISCORD_BOT_TOKEN": "discord-token",
            "DISCORD_OAUTH_CLIENT_ID": "discord-client-id",
        }
    )

    assert settings.discord_application_id == "discord-client-id"


def test_load_settings_does_not_require_a_discord_guild_id() -> None:
    settings = load_settings(
        {
            "DISCORD_BOT_TOKEN": "discord-token",
        }
    )

    assert settings.discord_guild_id is None


def test_load_settings_prefers_local_dotenv_over_stale_shell_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text(
        "\n".join(
            [
                "DISCORD_BOT_TOKEN=discord-token",
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
