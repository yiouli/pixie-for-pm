from pixie_for_pm.config.settings import load_settings
from pixie_for_pm.discord.normalization import (
    detect_mentioned_agents,
    detect_reply_agent,
)
from pixie_for_pm.domain.models import AgentRole


def test_detect_mentioned_agents_uses_persona_tokens() -> None:
    personas = load_settings(
        {
            "DISCORD_BOT_TOKEN": "discord-token",
            "DISCORD_GUILD_ID": "123",
            "DISCORD_ORCHESTRATION_CHANNEL_ID": "456",
            "DISCORD_PRODUCT_MANAGER_MENTION_TOKENS": "@pm",
            "DISCORD_USER_RESEARCHER_MENTION_TOKENS": "@uxr",
        }
    ).personas

    mentioned_agents = detect_mentioned_agents(
        "@uxr please work with @pm on interview follow-up.", personas
    )

    assert mentioned_agents == (
        AgentRole.PRODUCT_MANAGER,
        AgentRole.USER_RESEARCHER,
    )


def test_detect_reply_agent_matches_persona_display_name() -> None:
    personas = load_settings(
        {
            "DISCORD_BOT_TOKEN": "discord-token",
            "DISCORD_GUILD_ID": "123",
            "DISCORD_ORCHESTRATION_CHANNEL_ID": "456",
            "DISCORD_PRODUCT_DESIGNER_DISPLAY_NAME": "Pixie Designer",
        }
    ).personas

    reply_agent = detect_reply_agent("Pixie Designer", personas)

    assert reply_agent is AgentRole.PRODUCT_DESIGNER
