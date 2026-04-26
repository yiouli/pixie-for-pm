from __future__ import annotations

from pixie_for_pm.config.settings import load_settings
from pixie_for_pm.discord.bot import PixieDiscordBot


def main() -> None:
    settings = load_settings()
    bot = PixieDiscordBot(settings)
    bot.run(settings.discord_bot_token)
