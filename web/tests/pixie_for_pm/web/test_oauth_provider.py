from __future__ import annotations

import base64
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest

from pixie_for_pm.config.settings import load_settings
from pixie_for_pm.web.providers.oauth import HttpOAuthService


def _settings() -> dict[str, str]:
    return {
        "DISCORD_BOT_TOKEN": "discord-token",
        "CREDENTIALS_ENCRYPTION_KEY": "j0aN3s-cLScfv0GfNyG8t0UyONn7y8u2s6o6cLs1hYw=",
        "OAUTH_CALLBACK_URL": "https://api.pixie.test/api/connections/oauth/callback",
        "NOTION_CLIENT_ID": "notion-client-id",
        "NOTION_CLIENT_SECRET": "notion-client-secret",
    }


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
