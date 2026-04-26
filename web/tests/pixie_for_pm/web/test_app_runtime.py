from fastapi.testclient import TestClient

from pixie_for_pm.config.settings import load_settings
from pixie_for_pm.web.app import create_app
from pixie_for_pm.web.store import InMemoryConnectionStore

_FERNET_KEY = "j0aN3s-cLScfv0GfNyG8t0UyONn7y8u2s6o6cLs1hYw="


def _settings() -> dict[str, str]:
    return {
        "DISCORD_BOT_TOKEN": "discord-token",
        "DISCORD_GUILD_ID": "123",
        "WEB_APP_URL": "https://app.pixie.test",
        "CREDENTIALS_ENCRYPTION_KEY": _FERNET_KEY,
        "SESSION_SECRET_KEY": _FERNET_KEY,
    }


class StubDiscordRuntime:
    def __init__(self) -> None:
        self.events: list[str] = []

    async def start(self) -> None:
        self.events.append("start")

    async def stop(self) -> None:
        self.events.append("stop")


def test_create_app_starts_and_stops_discord_runtime_with_lifespan() -> None:
    discord_runtime = StubDiscordRuntime()
    app = create_app(
        load_settings(_settings()),
        store=InMemoryConnectionStore(),
        discord_runtime=discord_runtime,
        enable_discord_bot=True,
    )

    with TestClient(app) as client:
        response = client.get("/healthz")

        assert response.status_code == 200
        assert discord_runtime.events == ["start"]

    assert discord_runtime.events == ["start", "stop"]


def test_create_app_does_not_start_discord_runtime_by_default() -> None:
    discord_runtime = StubDiscordRuntime()
    app = create_app(
        load_settings(_settings()),
        store=InMemoryConnectionStore(),
        discord_runtime=discord_runtime,
    )

    with TestClient(app) as client:
        response = client.get("/healthz")

        assert response.status_code == 200

    assert discord_runtime.events == []
