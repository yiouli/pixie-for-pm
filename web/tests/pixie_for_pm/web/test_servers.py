from fastapi.testclient import TestClient

from pixie_for_pm.config.settings import load_settings
from pixie_for_pm.web.app import create_app
from pixie_for_pm.web.auth import AuthenticatedUser, get_current_user
from pixie_for_pm.web.providers.discord_guilds import DiscordGuild
from pixie_for_pm.web.store import InMemoryConnectionStore

_FERNET_KEY = "j0aN3s-cLScfv0GfNyG8t0UyONn7y8u2s6o6cLs1hYw="

_OWNER = AuthenticatedUser(id="user-1", display_name="Pixie PM", email="pm@example.com")
_OTHER = AuthenticatedUser(
    id="user-2", display_name="Other User", email="other@example.com"
)


def _settings() -> dict[str, str]:
    return {
        "DISCORD_BOT_TOKEN": "discord-token",
        "WEB_APP_URL": "https://app.pixie.test",
        "CREDENTIALS_ENCRYPTION_KEY": _FERNET_KEY,
        "SESSION_SECRET_KEY": _FERNET_KEY,
    }


def _make_client(user: AuthenticatedUser) -> TestClient:
    """Return a TestClient with *user* as the authenticated user via dependency override."""
    store = InMemoryConnectionStore()
    app = create_app(load_settings(_settings()), store=store)
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


def test_claim_server_is_idempotent_for_owner() -> None:
    client = _make_client(_OWNER)

    first_response = client.post("/api/servers/server-123/claim")
    second_response = client.post("/api/servers/server-123/claim")

    assert first_response.status_code == 201
    assert second_response.status_code == 200
    assert second_response.json()["discord_server_id"] == "server-123"
    assert second_response.json()["owned_by_current_user"] is True


def test_get_server_reports_when_owned_by_another_user() -> None:
    # Two clients share the same store via the same app
    store = InMemoryConnectionStore()
    app = create_app(load_settings(_settings()), store=store)

    app.dependency_overrides[get_current_user] = lambda: _OWNER
    TestClient(app).post("/api/servers/server-123/claim")

    app.dependency_overrides[get_current_user] = lambda: _OTHER
    response = TestClient(app).get("/api/servers/server-123")

    assert response.status_code == 200
    assert response.json()["owned_by_current_user"] is False


def test_claim_server_conflicts_for_other_owner() -> None:
    store = InMemoryConnectionStore()
    app = create_app(load_settings(_settings()), store=store)

    app.dependency_overrides[get_current_user] = lambda: _OWNER
    TestClient(app).post("/api/servers/server-123/claim")

    app.dependency_overrides[get_current_user] = lambda: _OTHER
    response = TestClient(app).post("/api/servers/server-123/claim")

    assert response.status_code == 409


def test_list_servers_returns_owned_servers_only() -> None:
    client = _make_client(_OWNER)
    client.post("/api/servers/server-123/claim")

    response = client.get("/api/servers")

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": "server-1",
            "discord_server_id": "server-123",
            "icon_url": None,
            "name": None,
            "owned_by_current_user": True,
        }
    ]


class StubDiscordGuildService:
    async def get_guild(self, discord_server_id: str) -> DiscordGuild:
        return DiscordGuild(
            id=discord_server_id,
            name="BlueSoul",
            icon_url=(
                "https://cdn.discordapp.com/icons/"
                "server-123/abcdef0123456789.png?size=128"
            ),
        )


def test_claim_server_populates_discord_server_metadata() -> None:
    store = InMemoryConnectionStore()
    app = create_app(
        load_settings(_settings()),
        store=store,
        discord_guild_service=StubDiscordGuildService(),
    )
    app.dependency_overrides[get_current_user] = lambda: _OWNER

    client = TestClient(app)
    response = client.post("/api/servers/server-123/claim")

    assert response.status_code == 201
    assert response.json() == {
        "id": "server-1",
        "discord_server_id": "server-123",
        "icon_url": (
            "https://cdn.discordapp.com/icons/"
            "server-123/abcdef0123456789.png?size=128"
        ),
        "name": "BlueSoul",
        "owned_by_current_user": True,
    }

    persisted_response = client.get("/api/servers/server-123")

    assert persisted_response.status_code == 200
    assert persisted_response.json()["name"] == "BlueSoul"
    assert persisted_response.json()["icon_url"] == (
        "https://cdn.discordapp.com/icons/" "server-123/abcdef0123456789.png?size=128"
    )
