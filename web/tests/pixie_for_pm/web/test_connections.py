from fastapi.testclient import TestClient

from pixie_for_pm.config.settings import load_settings
from pixie_for_pm.web.app import create_app
from pixie_for_pm.web.auth import AuthenticatedUser, get_current_user
from pixie_for_pm.web.encryption import CredentialCipher
from pixie_for_pm.web.providers.api_key import MappingApiKeyValidator
from pixie_for_pm.web.providers.oauth import StaticOAuthService
from pixie_for_pm.web.store import InMemoryConnectionStore

_FERNET_KEY = "j0aN3s-cLScfv0GfNyG8t0UyONn7y8u2s6o6cLs1hYw="
_OWNER = AuthenticatedUser(id="user-1", display_name="Pixie PM", email="pm@example.com")


def _settings() -> dict[str, str]:
    return {
        "DISCORD_BOT_TOKEN": "discord-token",
        "DISCORD_GUILD_ID": "123",
        "DISCORD_ORCHESTRATION_CHANNEL_ID": "456",
        "WEB_APP_URL": "https://app.pixie.test",
        "CREDENTIALS_ENCRYPTION_KEY": _FERNET_KEY,
        "SESSION_SECRET_KEY": _FERNET_KEY,
        "OAUTH_CALLBACK_URL": "https://api.pixie.test/api/connections/oauth/callback",
        "GITHUB_CLIENT_ID": "github-id",
        "GITHUB_CLIENT_SECRET": "github-secret",
    }


def _make_store() -> InMemoryConnectionStore:
    return InMemoryConnectionStore()


def _client(store: InMemoryConnectionStore | None = None) -> TestClient:
    """Return a TestClient authenticated as _OWNER with a claimed server."""
    runtime_store = store or _make_store()
    app = create_app(
        load_settings(_settings()),
        store=runtime_store,
        api_key_validator=MappingApiKeyValidator(
            {
                "posthog": [
                    {
                        "api_key": "posthog-key",
                        "project_id": "project-123",
                        "host": "https://us.posthog.com",
                    }
                ]
            }
        ),
        oauth_service=StaticOAuthService(
            authorize_urls={
                "github": "https://github.com/login/oauth/authorize?client_id=github-id"
            },
            token_payloads={
                "github": {
                    "access_token": "oauth-access-token",
                    "refresh_token": "oauth-refresh-token",
                    "token_type": "bearer",
                }
            },
        ),
    )
    app.dependency_overrides[get_current_user] = lambda: _OWNER
    client = TestClient(app)
    client.post("/api/servers/server-123/claim")
    return client


def test_save_api_key_connection_encrypts_and_stores_credentials() -> None:
    store = _make_store()
    client = _client(store)
    cipher = CredentialCipher(_FERNET_KEY)

    save_response = client.post(
        "/api/connections/posthog?server_id=server-123",
        json={
            "api_key": "posthog-key",
            "project_id": "project-123",
            "host": "https://us.posthog.com",
        },
    )
    list_response = client.get("/api/connections?server_id=server-123")

    # Verify the credentials are retrievable directly from the store (no HTTP hop)
    import asyncio

    connection = asyncio.get_event_loop().run_until_complete(
        store.get_connection_by_discord_server("server-123", "posthog")
    )
    assert connection is not None
    decrypted = cipher.decrypt_credentials(connection.credentials_encrypted)

    assert save_response.status_code == 200
    assert list_response.json() == [
        {
            "provider": "posthog",
            "status": "active",
            "connected_at": "2026-01-01T00:00:00+00:00",
            "last_used_at": None,
        }
    ]
    assert decrypted == {
        "api_key": "posthog-key",
        "project_id": "project-123",
        "host": "https://us.posthog.com",
    }


def test_oauth_authorize_and_callback_store_tokens_and_redirect_back_to_settings() -> (
    None
):
    store = _make_store()
    client = _client(store)
    cipher = CredentialCipher(_FERNET_KEY)

    authorize_response = client.get(
        "/api/connections/github/authorize?server_id=server-123",
        follow_redirects=False,
    )
    callback_response = client.get(
        "/api/connections/oauth/callback",
        params={
            "provider": "github",
            "code": "code-123",
            "state": authorize_response.headers["Location"].split("state=")[1],
        },
        follow_redirects=False,
    )

    # Verify tokens are stored encrypted in the store (not fetched over HTTP)
    import asyncio

    connection = asyncio.get_event_loop().run_until_complete(
        store.get_connection_by_discord_server("server-123", "github")
    )
    assert connection is not None
    decrypted = cipher.decrypt_credentials(connection.credentials_encrypted)

    assert authorize_response.status_code == 302
    assert authorize_response.headers["Location"].startswith(
        "https://github.com/login/oauth/authorize?client_id=github-id"
    )
    assert callback_response.status_code == 302
    assert callback_response.headers["Location"] == (
        "https://app.pixie.test/settings?server_id=server-123&connected=github"
    )
    assert decrypted == {
        "access_token": "oauth-access-token",
        "refresh_token": "oauth-refresh-token",
        "token_type": "bearer",
    }


def test_disconnect_removes_credentials_from_store() -> None:
    store = _make_store()
    client = _client(store)

    client.post(
        "/api/connections/posthog?server_id=server-123",
        json={
            "api_key": "posthog-key",
            "project_id": "project-123",
            "host": "https://us.posthog.com",
        },
    )
    delete_response = client.delete("/api/connections/posthog?server_id=server-123")

    import asyncio

    connection = asyncio.get_event_loop().run_until_complete(
        store.get_connection_by_discord_server("server-123", "posthog")
    )

    assert delete_response.status_code == 204
    assert connection is None
