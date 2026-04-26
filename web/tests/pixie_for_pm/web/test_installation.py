from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

from pixie_for_pm.config.settings import load_settings
from pixie_for_pm.web.app import create_app
from pixie_for_pm.web.store import InMemoryConnectionStore

_FERNET_KEY = "j0aN3s-cLScfv0GfNyG8t0UyONn7y8u2s6o6cLs1hYw="


def _settings() -> dict[str, str]:
    return {
        "DISCORD_BOT_TOKEN": "discord-token",
        "DISCORD_APPLICATION_ID": "discord-app-id",
        "WEB_APP_URL": "https://app.pixie.test",
        "CREDENTIALS_ENCRYPTION_KEY": _FERNET_KEY,
        "SESSION_SECRET_KEY": _FERNET_KEY,
    }


def test_discord_install_redirects_to_callbackless_bot_authorize_url() -> None:
    app = create_app(load_settings(_settings()), store=InMemoryConnectionStore())

    response = TestClient(app).get("/api/discord/install", follow_redirects=False)

    location = response.headers["Location"]
    parsed = urlparse(location)
    query = parse_qs(parsed.query)

    assert response.status_code == 302
    assert parsed.scheme == "https"
    assert parsed.netloc == "discord.com"
    assert parsed.path == "/oauth2/authorize"
    assert query == {
        "client_id": ["discord-app-id"],
        "scope": ["bot applications.commands"],
        "permissions": ["309237713920"],
    }


def test_discord_install_requires_a_configured_application_id() -> None:
    settings = _settings()
    del settings["DISCORD_APPLICATION_ID"]
    settings.pop("DISCORD_OAUTH_CLIENT_ID", None)
    app = create_app(load_settings(settings), store=InMemoryConnectionStore())

    response = TestClient(app).get("/api/discord/install")

    assert response.status_code == 503
    assert response.json() == {
        "detail": "Discord bot installation is not configured on this server."
    }
