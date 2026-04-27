from __future__ import annotations

import base64
import hashlib
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest

from pixie_for_pm.config.settings import load_settings
from pixie_for_pm.web.providers.oauth import (
    HttpOAuthService,
    exchange_notion_mcp_code,
    prepare_notion_mcp_authorization,
)


def _settings() -> dict[str, str]:
    return {
        "DISCORD_BOT_TOKEN": "discord-token",
        "CREDENTIALS_ENCRYPTION_KEY": "j0aN3s-cLScfv0GfNyG8t0UyONn7y8u2s6o6cLs1hYw=",
        "OAUTH_CALLBACK_URL": "https://api.pixie.test/api/connections/oauth/callback",
        "NOTION_CLIENT_ID": "notion-client-id",
        "NOTION_CLIENT_SECRET": "notion-client-secret",
    }


def _vercel_settings() -> dict[str, str]:
    settings = _settings()
    settings.update(
        {
            "VERCEL_CLIENT_ID": "vercel-client-id",
            "VERCEL_CLIENT_SECRET": "vercel-client-secret",
        }
    )
    return settings


def test_notion_authorize_url_includes_required_owner_parameter() -> None:
    service = HttpOAuthService(load_settings(_settings()))

    authorize_url = service.get_authorize_url("notion", "signed-state")
    query = parse_qs(urlsplit(authorize_url).query)

    assert query["client_id"] == ["notion-client-id"]
    assert query["redirect_uri"] == [
        "https://api.pixie.test/api/connections/oauth/callback"
    ]
    assert query["response_type"] == ["code"]
    assert query["owner"] == ["user"]
    assert query["state"] == ["signed-state"]


@pytest.mark.asyncio
async def test_prepare_notion_mcp_authorization_uses_discovery_registration_and_pkce(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class _FakeResponse:
        def __init__(self, status_code: int, payload: dict[str, Any]) -> None:
            self.status_code = status_code
            self._payload = payload

        def json(self) -> dict[str, Any]:
            return self._payload

        @property
        def text(self) -> str:
            return str(self._payload)

    class _FakeAsyncClient:
        def __init__(self, *, timeout: float) -> None:
            assert timeout == 15.0

        async def __aenter__(self) -> _FakeAsyncClient:
            return self

        async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

        async def get(self, url: str) -> _FakeResponse:
            captured.setdefault("gets", []).append(url)
            if url == "https://mcp.notion.com/.well-known/oauth-protected-resource":
                return _FakeResponse(
                    200,
                    {"authorization_servers": ["https://mcp.notion.com"]},
                )
            if url == "https://mcp.notion.com/.well-known/oauth-authorization-server":
                return _FakeResponse(
                    200,
                    {
                        "authorization_endpoint": "https://mcp.notion.com/authorize",
                        "token_endpoint": "https://mcp.notion.com/token",
                        "registration_endpoint": "https://mcp.notion.com/register",
                    },
                )
            raise AssertionError(url)

        async def post(
            self,
            url: str,
            *,
            headers: dict[str, str],
            json: dict[str, Any] | None = None,
            data: dict[str, str] | None = None,
        ) -> _FakeResponse:
            captured["post_url"] = url
            captured["post_headers"] = headers
            captured["post_json"] = json
            captured["post_data"] = data
            return _FakeResponse(
                200,
                {
                    "client_id": "registered-client-id",
                    "client_secret": "registered-client-secret",
                },
            )

    monkeypatch.setattr(
        "pixie_for_pm.web.providers.oauth.httpx.AsyncClient",
        _FakeAsyncClient,
    )

    prepared = await prepare_notion_mcp_authorization(
        state="signed-state",
        redirect_uri="https://api.pixie.test/api/connections/oauth/callback",
        client_name="Pixie",
        client_uri="https://app.pixie.test",
    )
    query = parse_qs(urlsplit(prepared.authorize_url).query)

    assert captured["gets"] == [
        "https://mcp.notion.com/.well-known/oauth-protected-resource",
        "https://mcp.notion.com/.well-known/oauth-authorization-server",
    ]
    assert captured["post_url"] == "https://mcp.notion.com/register"
    assert captured["post_headers"] == {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    assert captured["post_json"] == {
        "client_name": "Pixie",
        "client_uri": "https://app.pixie.test",
        "redirect_uris": ["https://api.pixie.test/api/connections/oauth/callback"],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
    }
    assert prepared.client_id == "registered-client-id"
    assert prepared.client_secret == "registered-client-secret"
    assert prepared.code_verifier != ""
    assert query["client_id"] == ["registered-client-id"]
    assert query["redirect_uri"] == [
        "https://api.pixie.test/api/connections/oauth/callback"
    ]
    assert query["state"] == ["signed-state"]
    assert query["code_challenge_method"] == ["S256"]
    assert query["prompt"] == ["consent"]
    assert "code_challenge" in query


@pytest.mark.asyncio
async def test_exchange_notion_mcp_code_uses_discovered_token_endpoint_and_pkce(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class _FakeResponse:
        def __init__(self, status_code: int, payload: dict[str, Any]) -> None:
            self.status_code = status_code
            self._payload = payload

        def json(self) -> dict[str, Any]:
            return self._payload

        @property
        def text(self) -> str:
            return str(self._payload)

    class _FakeAsyncClient:
        def __init__(self, *, timeout: float) -> None:
            assert timeout == 15.0

        async def __aenter__(self) -> _FakeAsyncClient:
            return self

        async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

        async def get(self, url: str) -> _FakeResponse:
            captured.setdefault("gets", []).append(url)
            if url == "https://mcp.notion.com/.well-known/oauth-protected-resource":
                return _FakeResponse(
                    200,
                    {"authorization_servers": ["https://mcp.notion.com"]},
                )
            if url == "https://mcp.notion.com/.well-known/oauth-authorization-server":
                return _FakeResponse(
                    200,
                    {
                        "authorization_endpoint": "https://mcp.notion.com/authorize",
                        "token_endpoint": "https://mcp.notion.com/token",
                    },
                )
            raise AssertionError(url)

        async def post(
            self,
            url: str,
            *,
            headers: dict[str, str],
            json: dict[str, Any] | None = None,
            data: dict[str, str] | None = None,
        ) -> _FakeResponse:
            captured["post_url"] = url
            captured["post_headers"] = headers
            captured["post_json"] = json
            captured["post_data"] = data
            return _FakeResponse(
                200,
                {
                    "access_token": "mcp-access-token",
                    "refresh_token": "mcp-refresh-token",
                    "token_type": "bearer",
                    "scope": "read write",
                },
            )

    monkeypatch.setattr(
        "pixie_for_pm.web.providers.oauth.httpx.AsyncClient",
        _FakeAsyncClient,
    )

    payload, scopes = await exchange_notion_mcp_code(
        code="temporary-code",
        redirect_uri="https://api.pixie.test/api/connections/oauth/callback",
        code_verifier="notion-code-verifier",
        client_id="registered-client-id",
        client_secret="registered-client-secret",
    )

    assert payload == {
        "access_token": "mcp-access-token",
        "refresh_token": "mcp-refresh-token",
        "token_type": "bearer",
        "scope": "read write",
    }
    assert scopes == ["read", "write"]
    assert captured["post_url"] == "https://mcp.notion.com/token"
    assert captured["post_json"] is None
    assert captured["post_data"] == {
        "grant_type": "authorization_code",
        "code": "temporary-code",
        "client_id": "registered-client-id",
        "client_secret": "registered-client-secret",
        "redirect_uri": "https://api.pixie.test/api/connections/oauth/callback",
        "code_verifier": "notion-code-verifier",
    }
    assert captured["post_headers"] == {
        "Accept": "application/json",
        "Content-Type": "application/x-www-form-urlencoded",
    }


@pytest.mark.asyncio
async def test_notion_token_exchange_uses_basic_auth_and_json_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = HttpOAuthService(load_settings(_settings()))
    captured: dict[str, Any] = {}

    class _FakeResponse:
        status_code = 200

        def json(self) -> dict[str, str]:
            return {
                "access_token": "notion-access-token",
                "refresh_token": "notion-refresh-token",
                "workspace_id": "workspace-123",
            }

    class _FakeAsyncClient:
        def __init__(self, *, timeout: float) -> None:
            assert timeout == 15.0

        async def __aenter__(self) -> _FakeAsyncClient:
            return self

        async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

        async def post(
            self,
            url: str,
            *,
            data: dict[str, str] | None = None,
            json: dict[str, str] | None = None,
            headers: dict[str, str],
        ) -> _FakeResponse:
            captured["url"] = url
            captured["data"] = data
            captured["json"] = json
            captured["headers"] = headers
            return _FakeResponse()

    monkeypatch.setattr(
        "pixie_for_pm.web.providers.oauth.httpx.AsyncClient",
        _FakeAsyncClient,
    )

    payload, scopes = await service.exchange_code("notion", "temporary-code")

    assert payload == {
        "access_token": "notion-access-token",
        "refresh_token": "notion-refresh-token",
        "workspace_id": "workspace-123",
    }
    assert scopes is None
    assert captured["url"] == "https://api.notion.com/v1/oauth/token"
    assert captured["data"] is None
    assert captured["json"] == {
        "grant_type": "authorization_code",
        "code": "temporary-code",
        "redirect_uri": "https://api.pixie.test/api/connections/oauth/callback",
    }
    assert captured["headers"] == {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": "Basic "
        + base64.b64encode(b"notion-client-id:notion-client-secret").decode(),
    }


def test_vercel_authorize_url_includes_pkce_challenge() -> None:
    service = HttpOAuthService(load_settings(_vercel_settings()))
    verifier = "vercel-test-verifier"

    authorize_url = service.get_authorize_url(
        "vercel",
        "signed-state",
        code_challenge=base64.urlsafe_b64encode(
            hashlib.sha256(verifier.encode()).digest()
        )
        .decode()
        .rstrip("="),
    )
    query = parse_qs(urlsplit(authorize_url).query)

    assert query["client_id"] == ["vercel-client-id"]
    assert query["redirect_uri"] == [
        "https://api.pixie.test/api/connections/oauth/callback"
    ]
    assert query["state"] == ["signed-state"]
    assert query["code_challenge_method"] == ["S256"]
    assert "code_challenge" in query


@pytest.mark.asyncio
async def test_vercel_token_exchange_uses_login_endpoint_and_pkce_verifier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = HttpOAuthService(load_settings(_vercel_settings()))
    captured: dict[str, Any] = {}

    class _FakeResponse:
        status_code = 200

        def json(self) -> dict[str, str]:
            return {
                "access_token": "vercel-access-token",
                "refresh_token": "vercel-refresh-token",
                "token_type": "bearer",
            }

    class _FakeAsyncClient:
        def __init__(self, *, timeout: float) -> None:
            assert timeout == 15.0

        async def __aenter__(self) -> Any:
            return self

        async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

        async def post(
            self,
            url: str,
            *,
            data: dict[str, str] | None = None,
            json: dict[str, str] | None = None,
            headers: dict[str, str],
        ) -> _FakeResponse:
            captured["url"] = url
            captured["data"] = data
            captured["json"] = json
            captured["headers"] = headers
            return _FakeResponse()

    monkeypatch.setattr(
        "pixie_for_pm.web.providers.oauth.httpx.AsyncClient",
        _FakeAsyncClient,
    )

    payload, scopes = await service.exchange_code(
        "vercel",
        "temporary-code",
        code_verifier="vercel-test-verifier",
    )

    assert payload == {
        "access_token": "vercel-access-token",
        "refresh_token": "vercel-refresh-token",
        "token_type": "bearer",
    }
    assert scopes is None
    assert captured["url"] == "https://api.vercel.com/login/oauth/token"
    assert captured["json"] is None
    assert captured["data"] == {
        "grant_type": "authorization_code",
        "code": "temporary-code",
        "redirect_uri": "https://api.pixie.test/api/connections/oauth/callback",
        "client_id": "vercel-client-id",
        "client_secret": "vercel-client-secret",
        "code_verifier": "vercel-test-verifier",
    }
    assert captured["headers"] == {"Accept": "application/json"}
