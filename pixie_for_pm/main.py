from __future__ import annotations

import uvicorn
from fastapi import FastAPI

from pixie_for_pm.config.settings import load_settings
from pixie_for_pm.web.app import create_app


def build_app(*, start_discord_bot: bool = False) -> FastAPI:
    return create_app(load_settings(), enable_discord_bot=start_discord_bot)


def run_server(*, start_discord_bot: bool) -> None:
    uvicorn.run(
        build_app(start_discord_bot=start_discord_bot), host="0.0.0.0", port=8000
    )


def main() -> None:
    run_server(start_discord_bot=True)
