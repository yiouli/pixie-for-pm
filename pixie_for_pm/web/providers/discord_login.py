"""Discord OAuth login service.

Handles the two-leg Discord authorization-code flow used to authenticate users
in the settings web app:

1. :meth:`DiscordLoginService.build_authorize_url` — build the Discord OAuth
   consent-screen URL that the browser is redirected to.
2. :meth:`DiscordLoginService.exchange_code` — exchange the authorization code
   for a Discord access token, then call the Discord ``/users/@me`` endpoint to
   retrieve the authenticated user's identity.

A :class:`StaticDiscordLoginService` test double is provided so that tests
never make live network calls.  The production :class:`HttpDiscordLoginService`
uses ``httpx`` and can be given an injectable transport for integration tests.
"""

from __future__ import annotations

import urllib.parse
from dataclasses import dataclass
from typing import Protocol

import httpx


@dataclass(frozen=True)
class DiscordUser:
    """Minimal Discord user identity returned after a successful OAuth login."""

    id: str
    username: str
    global_name: str | None
    email: str | None


class DiscordLoginError(Exception):
    """Raised when the Discord OAuth exchange or user-info fetch fails."""


class DiscordLoginService(Protocol):
    """Dependency-injectable interface for Discord OAuth login."""

    def build_authorize_url(self, *, callback_url: str, state: str) -> str:
        """Return the Discord consent-screen URL."""
        ...

    async def exchange_code(self, code: str, *, callback_url: str) -> DiscordUser:
        """Exchange *code* and return the authenticated :class:`DiscordUser`.

        Raises :exc:`DiscordLoginError` on any API failure.
        """
        ...


# ---------------------------------------------------------------------------
# Test double
# ---------------------------------------------------------------------------


class StaticDiscordLoginService:
    """Test double that returns a predetermined user without network calls.

    ``authorize_url_template`` may contain ``{state}`` which is filled in by
    :meth:`build_authorize_url`.  If *user* is ``None``, :meth:`exchange_code`
    raises :exc:`DiscordLoginError` (simulates a failed exchange).
    """

    def __init__(
        self,
        *,
        authorize_url_template: str = "https://discord.com/api/oauth2/authorize?state={state}",
        user: DiscordUser | None = None,
    ) -> None:
        self._authorize_url_template = authorize_url_template
        self._user = user

    def build_authorize_url(self, *, callback_url: str, state: str) -> str:
        del callback_url
        return self._authorize_url_template.format(state=state)

    async def exchange_code(self, code: str, *, callback_url: str) -> DiscordUser:
        del code, callback_url
        if self._user is None:
            raise DiscordLoginError(
                "exchange_code is not configured in this test double"
            )
        return self._user


# ---------------------------------------------------------------------------
# Production implementation
# ---------------------------------------------------------------------------

_DISCORD_AUTHORIZE_URL = "https://discord.com/api/oauth2/authorize"
_DISCORD_TOKEN_URL = "https://discord.com/api/oauth2/token"
_DISCORD_USER_URL = "https://discord.com/api/users/@me"


class HttpDiscordLoginService:
    """Production Discord OAuth login service backed by ``httpx``.

    Args:
        client_id: The Discord application's client ID.
        client_secret: The Discord application's client secret.
        transport: Optional ``httpx`` transport override for integration tests.
    """

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._transport = transport

    def build_authorize_url(self, *, callback_url: str, state: str) -> str:
        params = urllib.parse.urlencode(
            {
                "client_id": self._client_id,
                "redirect_uri": callback_url,
                "response_type": "code",
                "scope": "identify email",
                "state": state,
            }
        )
        return f"{_DISCORD_AUTHORIZE_URL}?{params}"

    async def exchange_code(self, code: str, *, callback_url: str) -> DiscordUser:
        async with httpx.AsyncClient(transport=self._transport, timeout=15.0) as client:
            token_response = await client.post(
                _DISCORD_TOKEN_URL,
                data={
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": callback_url,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            if token_response.status_code != 200:
                raise DiscordLoginError(
                    f"Discord token exchange failed: {token_response.status_code}"
                )
            token_data = token_response.json()
            access_token: str = token_data["access_token"]

            user_response = await client.get(
                _DISCORD_USER_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if user_response.status_code != 200:
                raise DiscordLoginError(
                    f"Discord user fetch failed: {user_response.status_code}"
                )
            user_data = user_response.json()

        return DiscordUser(
            id=str(user_data["id"]),
            username=str(user_data["username"]),
            global_name=user_data.get("global_name"),
            email=user_data.get("email"),
        )
