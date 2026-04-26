"""Settings web server for Pixie PM.

This module provides :func:`create_app`, an injectable factory that assembles
the FastAPI application, and :func:`main`, the entry point registered as
``pixie-web-server`` in ``pyproject.toml``. When a built front-end bundle is
present in ``web/dist``, the same FastAPI process serves that SPA and falls
back to ``index.html`` for client-side routes.

Architecture
------------
The web server exposes a settings API for Discord server owners to connect
external tools (Notion, GitHub, PostHog, etc.) to their server.  It is a
Python process that runs **alongside** the Discord bot process.  Both processes
can share the same :class:`~pixie_for_pm.web.store.ConnectionStore` instance
(Supabase or in-memory) and :class:`~pixie_for_pm.web.encryption.CredentialCipher`
directly in Python code — no HTTP bridge is needed.

Authentication
--------------
Users log in via Discord OAuth 2.0 (``GET /api/auth/discord`` →
``GET /api/auth/discord/callback``).  On success the server sets a signed
Fernet-encrypted ``session`` HttpOnly cookie.  All protected routes read this
cookie via the :func:`~pixie_for_pm.web.auth.get_current_user` dependency.

Credential storage
------------------
OAuth tokens and API keys are encrypted with
:class:`~pixie_for_pm.web.encryption.CredentialCipher` (Fernet) before being
written to the store.  The agent runtime decrypts them **directly in Python**
by importing the same cipher — see
:mod:`pixie_for_pm.integrations.credentials`.

Required environment variables
-------------------------------
- ``CREDENTIALS_ENCRYPTION_KEY`` — Fernet key for credential storage.
- ``SESSION_SECRET_KEY`` — Fernet key for session cookies.
- ``DISCORD_OAUTH_CLIENT_ID`` / ``DISCORD_OAUTH_CLIENT_SECRET`` — Discord app
  credentials for the login OAuth flow.
- ``DISCORD_OAUTH_CALLBACK_URL`` — public URL of ``/api/auth/discord/callback``.
- ``OAUTH_CALLBACK_URL`` — public URL of ``/api/connections/oauth/callback``
  (used by integration provider OAuth).
- ``WEB_APP_URL`` — public URL of the settings web app (used for CORS, the
    Discord `/settings` link, and post-login redirects).
- ``SUPABASE_URL`` / ``SUPABASE_SERVICE_ROLE_KEY`` — optional; enables the
  Supabase-backed connection store.  Falls back to in-memory when absent.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from pixie_for_pm.config.settings import AppSettings, load_settings
from pixie_for_pm.web.dependencies import WebAppServices
from pixie_for_pm.web.encryption import CredentialCipher
from pixie_for_pm.web.providers.api_key import HttpApiKeyValidator
from pixie_for_pm.web.providers.discord_login import (
    HttpDiscordLoginService,
    StaticDiscordLoginService,
)
from pixie_for_pm.web.providers.oauth import HttpOAuthService
from pixie_for_pm.web.routes.auth_routes import router as auth_router
from pixie_for_pm.web.routes.connection_routes import router as connection_router
from pixie_for_pm.web.routes.server_routes import router as server_router
from pixie_for_pm.web.session import SessionCodec
from pixie_for_pm.web.store import InMemoryConnectionStore, SupabaseConnectionStore

if TYPE_CHECKING:
    from pixie_for_pm.web.providers.api_key import ApiKeyValidator
    from pixie_for_pm.web.providers.discord_login import DiscordLoginService
    from pixie_for_pm.web.providers.oauth import OAuthService
    from pixie_for_pm.web.store import ConnectionStore


def _default_frontend_dist_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "web" / "dist"


def _resolve_frontend_asset(frontend_dist_dir: Path, request_path: str) -> Path | None:
    if request_path == "":
        candidate = frontend_dist_dir / "index.html"
    else:
        candidate = (frontend_dist_dir / request_path).resolve()
        try:
            candidate.relative_to(frontend_dist_dir.resolve())
        except ValueError:
            return None
    if candidate.is_file():
        return candidate
    return None


def create_app(
    settings: AppSettings,
    *,
    store: ConnectionStore | None = None,
    discord_login_service: DiscordLoginService | None = None,
    api_key_validator: ApiKeyValidator | None = None,
    oauth_service: OAuthService | None = None,
    frontend_dist_dir: Path | None = None,
) -> FastAPI:
    """Assemble and return the FastAPI application.

    All injectable parameters default to reasonable production implementations
    when ``None``.  Pass test doubles here in tests to avoid live network calls.

    Args:
        settings: Loaded application settings.
        store: Connection store override.  Defaults to
            :class:`~pixie_for_pm.web.store.SupabaseConnectionStore` when
            ``SUPABASE_URL`` and ``SUPABASE_SERVICE_ROLE_KEY`` are set, or
            :class:`~pixie_for_pm.web.store.InMemoryConnectionStore` otherwise.
        discord_login_service: Discord OAuth login service override.  Defaults
            to :class:`~pixie_for_pm.web.providers.discord_login.HttpDiscordLoginService`
            when Discord OAuth credentials are configured.
        api_key_validator: API key validator override.
        oauth_service: Integration-provider OAuth service override.
    """
    if settings.credentials_encryption_key is None:
        raise ValueError(
            "CREDENTIALS_ENCRYPTION_KEY must be configured for the web app."
        )
    if settings.session_secret_key is None:
        raise ValueError("SESSION_SECRET_KEY must be configured for the web app.")

    runtime_store: ConnectionStore
    if store is not None:
        runtime_store = store
    elif settings.supabase_url and settings.supabase_service_role_key:
        runtime_store = SupabaseConnectionStore(
            settings.supabase_url,
            settings.supabase_service_role_key,
        )
    else:
        runtime_store = InMemoryConnectionStore()

    runtime_discord_login: DiscordLoginService
    if discord_login_service is not None:
        runtime_discord_login = discord_login_service
    elif (
        settings.discord_oauth_client_id is not None
        and settings.discord_oauth_client_secret is not None
    ):
        runtime_discord_login = HttpDiscordLoginService(
            settings.discord_oauth_client_id,
            settings.discord_oauth_client_secret,
        )
    else:
        runtime_discord_login = StaticDiscordLoginService()

    services = WebAppServices(
        settings=settings,
        store=runtime_store,
        discord_login_service=runtime_discord_login,
        session_codec=SessionCodec(settings.session_secret_key),
        api_key_validator=api_key_validator or HttpApiKeyValidator(),
        oauth_service=oauth_service or HttpOAuthService(settings),
        credential_cipher=CredentialCipher(settings.credentials_encryption_key),
    )

    app = FastAPI(title="Pixie PM Settings API")
    app.state.services = services

    if settings.web_app_url is not None:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=[settings.web_app_url],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(auth_router)
    app.include_router(server_router)
    app.include_router(connection_router)

    runtime_frontend_dist_dir = (
        frontend_dist_dir.resolve()
        if frontend_dist_dir is not None
        else _default_frontend_dist_dir().resolve()
    )

    if (
        runtime_frontend_dist_dir.is_dir()
        and (runtime_frontend_dist_dir / "index.html").is_file()
    ):

        @app.get("/", include_in_schema=False)
        async def serve_frontend_index() -> FileResponse:
            return FileResponse(runtime_frontend_dist_dir / "index.html")

        @app.get("/{full_path:path}", include_in_schema=False)
        async def serve_frontend(full_path: str) -> FileResponse:
            if full_path == "api" or full_path.startswith("api/"):
                raise HTTPException(status_code=404, detail="Not Found")

            asset = _resolve_frontend_asset(runtime_frontend_dist_dir, full_path)
            if asset is not None:
                return FileResponse(asset)

            return FileResponse(runtime_frontend_dist_dir / "index.html")

    return app


def main() -> None:
    settings = load_settings()
    uvicorn.run(create_app(settings), host="0.0.0.0", port=8000)
