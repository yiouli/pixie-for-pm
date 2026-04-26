"""Authentication routes.

Login flow
----------
1. ``GET /api/auth/discord`` — redirects the browser to Discord's OAuth consent
   screen.  A short-lived CSRF state value is stored in a ``_discord_state``
   cookie and embedded in the Discord ``state`` query parameter.
2. Discord redirects back to ``GET /api/auth/discord/callback?code=…&state=…``.
   The server verifies that *state* matches the cookie, exchanges the code for a
   Discord access token, fetches the user from Discord's ``/users/@me`` endpoint,
   then issues a ``session`` HttpOnly cookie and clears the CSRF state cookie.
   Finally the browser is redirected back to ``WEB_APP_URL``.
3. ``POST /api/auth/logout`` — clears the ``session`` cookie.

User info
---------
``GET /api/auth/me`` returns the authenticated user's profile decoded from the
session cookie.
"""

from __future__ import annotations

import hmac
import os
from typing import Annotated
from urllib.parse import quote, unquote

from fastapi import APIRouter, Cookie, HTTPException, Response
from fastapi.responses import RedirectResponse

from pixie_for_pm.web.auth import CurrentUserDep
from pixie_for_pm.web.dependencies import ServicesDep
from pixie_for_pm.web.providers.discord_login import DiscordLoginError
from pixie_for_pm.web.session import SessionUser

router = APIRouter(prefix="/api/auth", tags=["auth"])

_STATE_COOKIE = "_discord_state"
_NEXT_COOKIE = "_discord_next"
_STATE_COOKIE_MAX_AGE = 60 * 10  # 10 minutes


def _make_state() -> str:
    return os.urandom(32).hex()


def _states_match(a: str, b: str) -> bool:
    """Constant-time comparison to prevent timing oracle on state values."""
    return hmac.compare_digest(a, b)


def _normalize_next_path(next_path: str | None) -> str | None:
    if next_path is None:
        return None
    normalized = next_path.strip()
    if normalized == "":
        return None
    if normalized.startswith(("http://", "https://", "//")):
        raise HTTPException(status_code=400, detail="Invalid post-login redirect")
    if not normalized.startswith("/"):
        normalized = f"/{normalized}"
    return normalized


def _serialize_next_path(next_path: str) -> str:
    return quote(next_path, safe="")


def _deserialize_next_path(next_path: str | None) -> str | None:
    if next_path is None:
        return None
    return unquote(next_path)


@router.get("/discord")
async def discord_login(
    services: ServicesDep,
    next: str | None = None,
) -> RedirectResponse:
    """Start the Discord OAuth login flow.

    Generates a random CSRF state token, stores it in a short-lived
    ``_discord_state`` cookie, then redirects the browser to Discord's
    consent screen.

    Optional ``?next=<path>`` is embedded in the state so the callback
    can forward the browser to the right page after login.
    """
    if (
        services.settings.discord_oauth_client_id is None
        or services.settings.discord_oauth_client_secret is None
    ):
        raise HTTPException(
            status_code=503,
            detail="Discord OAuth is not configured on this server.",
        )
    if services.settings.discord_oauth_callback_url is None:
        raise HTTPException(
            status_code=503,
            detail="DISCORD_OAUTH_CALLBACK_URL is not configured.",
        )
    state = _make_state()
    next_path = _normalize_next_path(next)

    redirect = RedirectResponse(
        services.discord_login_service.build_authorize_url(
            callback_url=services.settings.discord_oauth_callback_url,
            state=state,
        ),
        status_code=302,
    )
    redirect.set_cookie(
        _STATE_COOKIE,
        state,
        max_age=_STATE_COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=services.settings.discord_oauth_callback_url.startswith("https"),
    )
    if next_path is not None:
        redirect.set_cookie(
            _NEXT_COOKIE,
            _serialize_next_path(next_path),
            max_age=_STATE_COOKIE_MAX_AGE,
            httponly=True,
            samesite="lax",
            secure=services.settings.discord_oauth_callback_url.startswith("https"),
        )
    return redirect


@router.get("/discord/callback")
async def discord_callback(
    services: ServicesDep,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
    discord_state: Annotated[str | None, Cookie(alias=_STATE_COOKIE)] = None,
    next_path: Annotated[str | None, Cookie(alias=_NEXT_COOKIE)] = None,
) -> RedirectResponse:
    """Handle the Discord OAuth callback.

    Verifies the CSRF state, exchanges the authorization code for a Discord
    access token, fetches the Discord user's identity, and issues a ``session``
    cookie.  The browser is then redirected to ``WEB_APP_URL``.
    """
    if error is not None:
        detail = f"Discord OAuth failed: {error}"
        if error_description:
            detail = f"{detail} ({error_description})"
        raise HTTPException(status_code=400, detail=detail)
    if code is None or state is None:
        raise HTTPException(
            status_code=400,
            detail="Discord OAuth callback is missing code or state.",
        )
    if discord_state is None or not _states_match(state, discord_state):
        raise HTTPException(status_code=400, detail="Invalid OAuth state")
    if services.settings.discord_oauth_callback_url is None:
        raise HTTPException(
            status_code=503,
            detail="DISCORD_OAUTH_CALLBACK_URL is not configured.",
        )
    if services.session_codec is None:
        raise HTTPException(
            status_code=503,
            detail="Session secret key is not configured.",
        )

    try:
        discord_user = await services.discord_login_service.exchange_code(
            code,
            callback_url=services.settings.discord_oauth_callback_url,
        )
    except DiscordLoginError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    session_token = services.session_codec.encode(
        SessionUser(
            discord_user_id=discord_user.id,
            display_name=discord_user.global_name or discord_user.username,
            email=discord_user.email,
        )
    )

    redirect_target = services.settings.web_app_url or "/"
    normalized_next_path = _normalize_next_path(_deserialize_next_path(next_path))
    if normalized_next_path:
        redirect_target = f"{redirect_target.rstrip('/')}{normalized_next_path}"

    final_response = RedirectResponse(redirect_target, status_code=302)
    final_response.set_cookie(
        "session",
        session_token,
        max_age=services.session_codec.DEFAULT_TTL_SECONDS,
        httponly=True,
        samesite="lax",
        secure=services.settings.discord_oauth_callback_url.startswith("https"),
    )
    final_response.delete_cookie(_STATE_COOKIE)
    final_response.delete_cookie(_NEXT_COOKIE)
    return final_response


@router.post("/logout")
async def logout() -> Response:
    """Clear the session cookie, ending the user's session."""
    response = Response(content="", status_code=204)
    response.delete_cookie("session")
    return response


@router.get("/me")
async def get_me(user: CurrentUserDep) -> dict[str, str | None]:
    """Return the authenticated user's profile."""
    return {
        "id": user.id,
        "display_name": user.display_name,
        "email": user.email,
    }
