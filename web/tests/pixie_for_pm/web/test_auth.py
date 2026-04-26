from urllib.parse import unquote

from fastapi.testclient import TestClient

from pixie_for_pm.config.settings import load_settings
from pixie_for_pm.web.app import create_app
from pixie_for_pm.web.auth import AuthenticatedUser, get_current_user
from pixie_for_pm.web.encryption import CredentialCipher
from pixie_for_pm.web.providers.discord_login import (
    DiscordUser,
    StaticDiscordLoginService,
)
from pixie_for_pm.web.session import SessionCodec, SessionUser
from pixie_for_pm.web.store import InMemoryConnectionStore

_FERNET_KEY = "j0aN3s-cLScfv0GfNyG8t0UyONn7y8u2s6o6cLs1hYw="


def _settings() -> dict[str, str]:
    return {
        "DISCORD_BOT_TOKEN": "discord-token",
        "DISCORD_GUILD_ID": "123",
        "WEB_APP_URL": "https://app.pixie.test",
        "CREDENTIALS_ENCRYPTION_KEY": _FERNET_KEY,
        "SESSION_SECRET_KEY": _FERNET_KEY,
        "DISCORD_OAUTH_CLIENT_ID": "discord-client-id",
        "DISCORD_OAUTH_CLIENT_SECRET": "discord-client-secret",
        "DISCORD_OAUTH_CALLBACK_URL": "http://api.pixie.test/api/auth/discord/callback",
    }


def _app_with_override(user: AuthenticatedUser) -> TestClient:
    """Return a TestClient where get_current_user is overridden to return *user*."""
    app = create_app(
        load_settings(_settings()),
        store=InMemoryConnectionStore(),
        discord_login_service=StaticDiscordLoginService(),
    )
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


def test_get_me_returns_profile_from_session() -> None:
    user = AuthenticatedUser(
        id="discord-123", display_name="Pixie PM", email="pm@example.com"
    )
    response = _app_with_override(user).get("/api/auth/me")

    assert response.status_code == 200
    assert response.json() == {
        "id": "discord-123",
        "display_name": "Pixie PM",
        "email": "pm@example.com",
    }


def test_get_me_rejects_missing_session_cookie() -> None:
    app = create_app(
        load_settings(_settings()),
        store=InMemoryConnectionStore(),
        discord_login_service=StaticDiscordLoginService(),
    )
    response = TestClient(app).get("/api/auth/me")

    assert response.status_code == 401


def test_discord_login_redirects_to_authorize_url_and_sets_state_cookie() -> None:
    app = create_app(
        load_settings(_settings()),
        store=InMemoryConnectionStore(),
        discord_login_service=StaticDiscordLoginService(
            authorize_url_template="https://discord.com/api/oauth2/authorize?state={state}"
        ),
    )
    response = TestClient(app).get(
        "/api/auth/discord",
        params={"next": "/settings?server_id=1459772566528069715"},
        follow_redirects=False,
    )
    state = response.headers["Location"].split("state=")[1]

    assert response.status_code == 302
    assert response.headers["Location"].startswith(
        "https://discord.com/api/oauth2/authorize?state="
    )
    assert "_discord_state" in response.cookies
    assert response.cookies["_discord_state"] == state
    assert unquote(response.cookies["_discord_next"].strip('"')) == (
        "/settings?server_id=1459772566528069715"
    )
    assert ":" not in state


def test_discord_callback_issues_session_cookie_and_redirects_to_web_app() -> None:
    discord_user = DiscordUser(
        id="discord-999",
        username="pixiepm",
        global_name="Pixie PM",
        email="pm@example.com",
    )
    app = create_app(
        load_settings(_settings()),
        store=InMemoryConnectionStore(),
        discord_login_service=StaticDiscordLoginService(user=discord_user),
    )
    client = TestClient(app, follow_redirects=False)

    # Step 1: start login to get the state cookie
    login_response = client.get(
        "/api/auth/discord",
        params={"next": "/settings?server_id=server-123"},
    )
    state = login_response.headers["Location"].split("state=")[1]

    # Step 2: simulate Discord callback
    callback_response = client.get(
        "/api/auth/discord/callback",
        params={"code": "auth-code-123", "state": state},
    )

    assert callback_response.status_code == 302
    assert callback_response.headers["Location"] == (
        "https://app.pixie.test/settings?server_id=server-123"
    )
    assert "session" in callback_response.cookies


def test_discord_callback_rejects_mismatched_state() -> None:
    app = create_app(
        load_settings(_settings()),
        store=InMemoryConnectionStore(),
        discord_login_service=StaticDiscordLoginService(),
    )
    client = TestClient(app)
    client.cookies.set("_discord_state", "different-state")

    response = client.get(
        "/api/auth/discord/callback",
        params={"code": "code", "state": "wrong-state"},
    )

    assert response.status_code == 400


def test_discord_callback_surfaces_discord_oauth_error_response() -> None:
    app = create_app(
        load_settings(_settings()),
        store=InMemoryConnectionStore(),
        discord_login_service=StaticDiscordLoginService(),
    )

    response = TestClient(app).get(
        "/api/auth/discord/callback",
        params={
            "error": "invalid_scope",
            "error_description": "The requested scope is invalid, unknown, or malformed.",
        },
    )

    assert response.status_code == 400
    assert response.json() == {
        "detail": (
            "Discord OAuth failed: invalid_scope "
            "(The requested scope is invalid, unknown, or malformed.)"
        )
    }


def test_logout_clears_session_cookie() -> None:
    user = AuthenticatedUser(id="discord-123", display_name="Pixie PM", email=None)
    client = _app_with_override(user)

    response = client.post("/api/auth/logout")

    assert response.status_code == 204
    # cookie should be cleared (set to empty / max_age=0)
    assert response.cookies.get("session", "") == ""


def test_session_codec_round_trips_user() -> None:
    codec = SessionCodec(_FERNET_KEY)
    user = SessionUser(
        discord_user_id="discord-42",
        display_name="Test User",
        email="test@example.com",
    )

    token = codec.encode(user)
    decoded = codec.decode(token)

    assert decoded is not None
    assert decoded.discord_user_id == "discord-42"
    assert decoded.display_name == "Test User"
    assert decoded.email == "test@example.com"


def test_session_codec_returns_none_for_expired_token() -> None:
    codec = SessionCodec(_FERNET_KEY)
    user = SessionUser(discord_user_id="u", display_name=None, email=None)
    token = codec.encode(user, ttl_seconds=-1)  # already expired

    assert codec.decode(token) is None


def test_credential_cipher_round_trips_json_payloads() -> None:
    cipher = CredentialCipher(_FERNET_KEY)
    encrypted = cipher.encrypt_credentials({"api_key": "secret", "project_id": "123"})
    decrypted = cipher.decrypt_credentials(encrypted)

    assert decrypted == {"api_key": "secret", "project_id": "123"}
