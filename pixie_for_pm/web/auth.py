"""Authentication for the settings web API.

Users authenticate with Discord via OAuth 2.0.  After completing the Discord
consent screen the callback route issues a signed, Fernet-encrypted HttpOnly
session cookie.  Subsequent requests carry that cookie automatically; the
:func:`get_current_user` FastAPI dependency decrypts it and returns the
authenticated user.

There is no server-side session table — sessions are stateless.  To revoke all
sessions (e.g. after a security incident) rotate ``SESSION_SECRET_KEY``.

Auth flow (implemented in :mod:`pixie_for_pm.web.routes.auth_routes`):

1. Browser → ``GET /api/auth/discord`` → redirect to Discord consent screen.
2. Discord → ``GET /api/auth/discord/callback?code=…&state=…``
3. Server exchanges code for Discord access token, calls ``/users/@me``,
   issues a ``session`` cookie, redirects browser to the settings web app.
4. Browser sends ``session`` cookie on all subsequent API requests.
5. ``POST /api/auth/logout`` clears the cookie.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Cookie, Depends, HTTPException

from pixie_for_pm.web.dependencies import ServicesDep


@dataclass(frozen=True)
class AuthenticatedUser:
    """Identity of the authenticated Discord user."""

    id: str
    """Discord user snowflake ID.  Used as ``owner_user_id`` in server records."""
    display_name: str | None
    email: str | None


async def get_current_user(
    services: ServicesDep,
    session: Annotated[str | None, Cookie()] = None,
) -> AuthenticatedUser:
    """FastAPI dependency that decodes the session cookie into an :class:`AuthenticatedUser`.

    Raises HTTP 401 if the cookie is absent, expired, or tampered with.
    """
    if session is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user = services.session_codec.decode(session)
    if user is None:
        raise HTTPException(status_code=401, detail="Session expired or invalid")
    return AuthenticatedUser(
        id=user.discord_user_id,
        display_name=user.display_name,
        email=user.email,
    )


CurrentUserDep = Annotated[AuthenticatedUser, Depends(get_current_user)]
