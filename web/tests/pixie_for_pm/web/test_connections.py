import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient

from pixie_for_pm.config.settings import load_settings
from pixie_for_pm.web.app import create_app
from pixie_for_pm.web.auth import AuthenticatedUser, get_current_user
from pixie_for_pm.web.encryption import CredentialCipher
from pixie_for_pm.web.providers.api_key import MappingApiKeyValidator
from pixie_for_pm.web.providers.discord_guilds import StaticDiscordGuildService
from pixie_for_pm.web.providers.oauth import StaticOAuthService
from pixie_for_pm.web.routes.connection_routes import _serialize_connection
from pixie_for_pm.web.store import ConnectionRecord, InMemoryConnectionStore

_FERNET_KEY = "j0aN3s-cLScfv0GfNyG8t0UyONn7y8u2s6o6cLs1hYw="
_OWNER = AuthenticatedUser(id="user-1", display_name="Pixie PM", email="pm@example.com")


def _settings() -> dict[str, str]:
    return {
        "DISCORD_BOT_TOKEN": "discord-token",
        "DISCORD_GUILD_ID": "123",
        "WEB_APP_URL": "https://app.pixie.test",
        "CREDENTIALS_ENCRYPTION_KEY": _FERNET_KEY,
        "SESSION_SECRET_KEY": _FERNET_KEY,
        "OAUTH_CALLBACK_URL": "https://api.pixie.test/api/connections/oauth/callback",
        "GITHUB_CLIENT_ID": "github-id",
        "GITHUB_CLIENT_SECRET": "github-secret",
    }


def _oauth_settings() -> dict[str, str]:
    settings = _settings()
    settings.update(
        {
            "WEB_APP_URL": "http://localhost:8000",
            "OAUTH_CALLBACK_URL": "http://localhost:8000/api/connections/oauth/callback",
            "VERCEL_CLIENT_ID": "vercel-id",
            "VERCEL_CLIENT_SECRET": "vercel-secret",
        }
    )
    return settings


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


def test_vercel_authorize_and_callback_use_mcp_flow_context_cookie(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _make_store()
    app = create_app(
        load_settings(_oauth_settings()),
        store=store,
        oauth_service=StaticOAuthService(authorize_urls={}, token_payloads={}),
    )
    app.dependency_overrides[get_current_user] = lambda: _OWNER
    client = TestClient(app, base_url="https://api.pixie.test")
    client.post("/api/servers/server-123/claim")
    cipher = CredentialCipher(_FERNET_KEY)

    class _PreparedAuthorization:
        def __init__(self, authorize_url: str) -> None:
            self.authorize_url = authorize_url
            self.code_verifier = "vercel-code-verifier"
            self.client_id = "vercel-registered-client-id"
            self.client_secret = None
            self.resource = "https://mcp.vercel.com/"

    async def _prepare(**kwargs: Any) -> _PreparedAuthorization:
        assert kwargs["client_id"] == "vercel-id"
        assert kwargs["client_secret"] == "vercel-secret"
        return _PreparedAuthorization(
            authorize_url="https://vercel.com/oauth/authorize?state=" + kwargs["state"]
        )

    async def _exchange(**kwargs: Any) -> tuple[dict[str, str], list[str] | None]:
        assert kwargs["code"] == "code-123"
        assert kwargs["client_id"] == "vercel-registered-client-id"
        assert kwargs["code_verifier"] == "vercel-code-verifier"
        assert kwargs["resource"] == "https://mcp.vercel.com/"
        return (
            {
                "access_token": "mcp-access-token",
                "refresh_token": "mcp-refresh-token",
                "token_type": "bearer",
            },
            ["openid", "offline_access"],
        )

    monkeypatch.setattr(
        "pixie_for_pm.web.routes.connection_routes.prepare_vercel_mcp_authorization",
        _prepare,
    )
    monkeypatch.setattr(
        "pixie_for_pm.web.routes.connection_routes.exchange_vercel_mcp_code",
        _exchange,
    )

    authorize_response = client.get(
        "/api/connections/vercel/authorize?server_id=server-123&response_mode=json",
        follow_redirects=False,
    )
    state = authorize_response.json()["authorize_url"].split("state=")[1]
    callback_response = client.get(
        "/api/connections/oauth/callback",
        params={
            "code": "code-123",
            "state": state,
        },
        follow_redirects=False,
    )


    connection = asyncio.get_event_loop().run_until_complete(
        store.get_connection_by_discord_server("server-123", "vercel")
    )
    assert connection is not None
    decrypted = cipher.decrypt_credentials(connection.credentials_encrypted)

    assert authorize_response.status_code == 200
    assert authorize_response.json() == {
        "authorize_url": f"https://vercel.com/oauth/authorize?state={state}"
    }
    assert "_oauth_notion_context" in authorize_response.headers.get("set-cookie", "")
    assert callback_response.status_code == 302
    assert callback_response.headers["Location"] == (
        "https://api.pixie.test/settings?server_id=server-123&connected=vercel"
    )
    assert decrypted == {
        "access_token": "mcp-access-token",
        "refresh_token": "mcp-refresh-token",
        "token_type": "bearer",
        "oauth_client_id": "vercel-registered-client-id",
        "oauth_resource": "https://mcp.vercel.com/",
    }


def test_notion_authorize_and_callback_use_mcp_flow_context_cookie(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _make_store()
    app = create_app(
        load_settings(_settings()),
        store=store,
        oauth_service=StaticOAuthService(
            authorize_urls={"notion": "https://unused.example/authorize"},
            token_payloads={},
        ),
    )
    app.dependency_overrides[get_current_user] = lambda: _OWNER
    client = TestClient(app, base_url="https://api.pixie.test")
    client.post("/api/servers/server-123/claim")
    cipher = CredentialCipher(_FERNET_KEY)

    class _PreparedAuthorization:
        def __init__(self, authorize_url: str) -> None:
            self.authorize_url = authorize_url
            self.code_verifier = "notion-code-verifier"
            self.client_id = "registered-client-id"
            self.client_secret = "registered-client-secret"
            self.resource = "https://mcp.notion.com"

    async def _prepare(**kwargs: Any) -> _PreparedAuthorization:
        return _PreparedAuthorization(
            authorize_url="https://mcp.notion.com/authorize?state=" + kwargs["state"]
        )

    async def _exchange(**kwargs: Any) -> tuple[dict[str, str], list[str] | None]:
        assert kwargs["code"] == "code-123"
        assert kwargs["client_id"] == "registered-client-id"
        assert kwargs["client_secret"] == "registered-client-secret"
        assert kwargs["code_verifier"] == "notion-code-verifier"
        assert kwargs["resource"] == "https://mcp.notion.com"
        return (
            {
                "access_token": "mcp-access-token",
                "refresh_token": "mcp-refresh-token",
                "token_type": "bearer",
            },
            ["read", "write"],
        )

    monkeypatch.setattr(
        "pixie_for_pm.web.routes.connection_routes.prepare_notion_mcp_authorization",
        _prepare,
    )
    monkeypatch.setattr(
        "pixie_for_pm.web.routes.connection_routes.exchange_notion_mcp_code",
        _exchange,
    )

    authorize_response = client.get(
        "/api/connections/notion/authorize?server_id=server-123&response_mode=json",
        follow_redirects=False,
    )
    state = authorize_response.json()["authorize_url"].split("state=")[1]
    callback_response = client.get(
        "/api/connections/oauth/callback",
        params={
            "code": "code-123",
            "state": state,
        },
        follow_redirects=False,
    )


    connection = asyncio.get_event_loop().run_until_complete(
        store.get_connection_by_discord_server("server-123", "notion")
    )
    assert connection is not None
    decrypted = cipher.decrypt_credentials(connection.credentials_encrypted)

    assert authorize_response.status_code == 200
    assert authorize_response.json() == {
        "authorize_url": f"https://mcp.notion.com/authorize?state={state}"
    }
    assert "_oauth_notion_context" in authorize_response.headers.get("set-cookie", "")
    assert callback_response.status_code == 302
    assert callback_response.headers["Location"] == (
        "https://app.pixie.test/settings?server_id=server-123&connected=notion"
    )
    assert decrypted == {
        "access_token": "mcp-access-token",
        "refresh_token": "mcp-refresh-token",
        "token_type": "bearer",
        "oauth_client_id": "registered-client-id",
        "oauth_client_secret": "registered-client-secret",
        "oauth_resource": "https://mcp.notion.com",
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


    connection = asyncio.get_event_loop().run_until_complete(
        store.get_connection_by_discord_server("server-123", "posthog")
    )

    assert delete_response.status_code == 204
    assert connection is None


@pytest.mark.asyncio
async def test_oauth_flow_prefers_request_host_over_localhost_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _make_store()
    app = create_app(
        load_settings(_oauth_settings()),
        store=store,
        discord_guild_service=StaticDiscordGuildService(),
    )
    app.dependency_overrides[get_current_user] = lambda: _OWNER
    captured: dict[str, Any] = {}

    class _PreparedAuthorization:
        def __init__(self, authorize_url: str) -> None:
            self.authorize_url = authorize_url
            self.code_verifier = "vercel-code-verifier"
            self.client_id = "vercel-registered-client-id"
            self.client_secret = None
            self.resource = "https://mcp.vercel.com/"

    async def _prepare(**kwargs: Any) -> _PreparedAuthorization:
        captured["prepare_redirect_uri"] = kwargs["redirect_uri"]
        return _PreparedAuthorization(
            authorize_url=(
                "https://vercel.com/oauth/authorize?redirect_uri="
                + kwargs["redirect_uri"]
                + "&state="
                + kwargs["state"]
            )
        )

    async def _exchange(**kwargs: Any) -> tuple[dict[str, str], list[str] | None]:
        captured["exchange_kwargs"] = kwargs
        return (
            {
                "access_token": "vercel-access-token",
                "refresh_token": "vercel-refresh-token",
                "token_type": "bearer",
            },
            ["openid", "offline_access"],
        )

    monkeypatch.setattr(
        "pixie_for_pm.web.routes.connection_routes.prepare_vercel_mcp_authorization",
        _prepare,
    )
    monkeypatch.setattr(
        "pixie_for_pm.web.routes.connection_routes.exchange_vercel_mcp_code",
        _exchange,
    )

    client = TestClient(app, base_url="https://pixie-preview.vercel.app")
    client.post("/api/servers/server-123/claim")

    authorize_response = client.get(
        "/api/connections/vercel/authorize?server_id=server-123",
        follow_redirects=False,
    )

    authorize_query = parse_qs(urlsplit(authorize_response.headers["Location"]).query)
    state = authorize_query["state"][0]

    callback_response = client.get(
        "/api/connections/oauth/callback",
        params={
            "code": "code-123",
            "state": state,
        },
        follow_redirects=False,
    )

    assert authorize_response.status_code == 302
    assert authorize_query["redirect_uri"] == [
        "https://pixie-preview.vercel.app/api/connections/oauth/callback"
    ]
    assert captured["prepare_redirect_uri"] == (
        "https://pixie-preview.vercel.app/api/connections/oauth/callback"
    )
    assert captured["exchange_kwargs"] == {
        "code": "code-123",
        "redirect_uri": "https://pixie-preview.vercel.app/api/connections/oauth/callback",
        "code_verifier": "vercel-code-verifier",
        "client_id": "vercel-registered-client-id",
        "client_secret": None,
        "resource": "https://mcp.vercel.com/",
    }
    assert callback_response.status_code == 302
    assert callback_response.headers["Location"] == (
        "https://pixie-preview.vercel.app/settings"
        "?server_id=server-123&connected=vercel"
    )


def _make_connection_record(credentials: dict[str, str]) -> ConnectionRecord:
    cipher = CredentialCipher(_FERNET_KEY)
    return ConnectionRecord(
        id="conn-1",
        server_id="server-1",
        provider="vercel",
        credentials_encrypted=cipher.encrypt_credentials(credentials),
        scopes=None,
        status="active",
        connected_at=datetime(2026, 1, 1, tzinfo=UTC),
        last_used_at=None,
    )


def test_serialize_connection_includes_access_expires_at_without_refresh_token() -> None:
    cipher = CredentialCipher(_FERNET_KEY)
    record = _make_connection_record(
        {"access_token": "tok", "expires_in": "3600"}
    )
    result = _serialize_connection(record, cipher)
    expected = (datetime(2026, 1, 1, tzinfo=UTC) + timedelta(seconds=3600)).isoformat()
    assert result["access_expires_at"] == expected


def test_serialize_connection_omits_access_expires_at_with_refresh_token() -> None:
    cipher = CredentialCipher(_FERNET_KEY)
    record = _make_connection_record(
        {"access_token": "tok", "expires_in": "3600", "refresh_token": "ref"}
    )
    result = _serialize_connection(record, cipher)
    assert "access_expires_at" not in result


def test_serialize_connection_omits_access_expires_at_without_expires_in() -> None:
    cipher = CredentialCipher(_FERNET_KEY)
    record = _make_connection_record({"access_token": "tok"})
    result = _serialize_connection(record, cipher)
    assert "access_expires_at" not in result
