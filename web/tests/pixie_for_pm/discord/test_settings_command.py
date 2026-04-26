import pytest

from pixie_for_pm.config.settings import load_settings
from pixie_for_pm.discord.commands.settings import build_settings_url


def test_build_settings_url_includes_guild_id_query_parameter() -> None:
    settings = load_settings(
        {
            "DISCORD_BOT_TOKEN": "discord-token",
            "WEB_APP_URL": "https://app.pixie.test",
        }
    )

    assert build_settings_url(settings, guild_id=987654321) == (
        "https://app.pixie.test/settings?server_id=987654321"
    )


def test_build_settings_url_requires_web_app_configuration() -> None:
    settings = load_settings(
        {
            "DISCORD_BOT_TOKEN": "discord-token",
        }
    )

    with pytest.raises(RuntimeError, match="WEB_APP_URL"):
        build_settings_url(settings, guild_id=987654321)
