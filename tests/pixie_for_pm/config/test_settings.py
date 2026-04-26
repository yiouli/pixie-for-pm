from pathlib import Path

from pixie_for_pm.config.settings import load_settings
from pixie_for_pm.domain.models import AgentRole


def test_load_settings_builds_personas_from_environment() -> None:
    settings = load_settings(
        {
            "DISCORD_BOT_TOKEN": "discord-token",
            "DISCORD_GUILD_ID": "123",
            "DISCORD_ORCHESTRATION_CHANNEL_ID": "456",
            "LANGGRAPH_CHECKPOINT_PATH": ".state/pixie.sqlite",
            "DISCORD_MARKET_ANALYST_MENTION_TOKENS": "@market-analyst,<@&42>",
            "DISCORD_MARKET_ANALYST_WEBHOOK_URL": "https://discord.com/api/webhooks/test",
        }
    )

    assert settings.discord_guild_id == 123
    assert settings.discord_orchestration_channel_id == 456
    assert settings.langgraph_checkpoint_path == Path(".state/pixie.sqlite")
    assert settings.personas[AgentRole.MARKET_ANALYST].mention_tokens == (
        "@market-analyst",
        "<@&42>",
    )
    assert (
        settings.personas[AgentRole.MARKET_ANALYST].webhook_url
        == "https://discord.com/api/webhooks/test"
    )
