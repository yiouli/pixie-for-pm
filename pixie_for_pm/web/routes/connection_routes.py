from __future__ import annotations

import base64
import json
from datetime import datetime, timedelta
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import APIRouter, Body, Cookie, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse

from pixie_for_pm.integrations.registry import PROVIDERS
from pixie_for_pm.web.auth import AuthenticatedUser, CurrentUserDep
from pixie_for_pm.web.dependencies import ServicesDep, WebAppServices
from pixie_for_pm.web.encryption import CredentialCipher
from pixie_for_pm.web.providers.api_key import InvalidApiKeyCredentialsError
from pixie_for_pm.web.providers.oauth import (
    InvalidOAuthStateError,
    OAuthProviderError,
    exchange_notion_mcp_code,
    prepare_notion_mcp_authorization,
)
from pixie_for_pm.web.store import ConnectionRecord, ServerRecord

router = APIRouter(prefix="/api/connections", tags=["connections"])

CredentialsBody = Annotated[dict[str, str], Body(...)]

_NOTION_CONTEXT_COOKIE = "_oauth_notion_context"
_PKCE_COOKIE_MAX_AGE = 60 * 10


def _format_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _serialize_connection(
    connection: ConnectionRecord,
    cipher: CredentialCipher | None = None,
) -> dict[str, str | None]:
    result: dict[str, str | None] = {
        "provider": connection.provider,
        "status": connection.status,
        "connected_at": connection.connected_at.isoformat(),
        "last_used_at": _format_datetime(connection.last_used_at),
    }
    if cipher is not None:
        try:
            creds = cipher.decrypt_credentials(connection.credentials_encrypted)
            if not creds.get("refresh_token"):
                expires_in_raw = creds.get("expires_in")
                if expires_in_raw is not None:
                    expires_at = connection.connected_at + timedelta(
                        seconds=int(expires_in_raw)
                    )
                    result["access_expires_at"] = expires_at.isoformat()
        except Exception:
            pass
    return result


async def _get_owned_server(
    services: WebAppServices,
    discord_server_id: str,
    user: AuthenticatedUser,
) -> ServerRecord:
    server = await services.store.get_server_by_discord_id(discord_server_id)
    if server is None:
        raise HTTPException(status_code=404, detail="Server is not claimed")
    if server.owner_user_id != user.id:
        raise HTTPException(status_code=403, detail="Not authorized for this server")
    return server


def _require_provider(provider: str) -> tuple[str, str]:
    config = PROVIDERS.get(provider)
    if config is None:
        raise HTTPException(status_code=404, detail="Unknown provider")
    return provider, config.auth_type


def _is_local_hostname(hostname: str | None) -> bool:
    return hostname in {"localhost", "127.0.0.1", "0.0.0.0"}


def _resolve_callback_url(request: Request, services: WebAppServices) -> str:
    configured_url = services.settings.oauth_callback_url
    if configured_url is None:
        return str(request.url_for("oauth_callback"))

    configured_host = urlsplit(configured_url).hostname
    request_host = request.url.hostname
    if _is_local_hostname(configured_host) and not _is_local_hostname(request_host):
        return str(request.url_for("oauth_callback"))
    return configured_url


def _resolve_settings_url(request: Request, services: WebAppServices) -> str:
    configured_url = services.settings.web_app_url
    if configured_url is None:
        return str(request.base_url).rstrip("/")

    configured_host = urlsplit(configured_url).hostname
    request_host = request.url.hostname
    if _is_local_hostname(configured_host) and not _is_local_hostname(request_host):
        return str(request.base_url).rstrip("/")
    return configured_url.rstrip("/")


def _provider_uses_hosted_mcp_oauth(provider: str) -> bool:
    return provider == "notion"


def _set_notion_context_cookie(
    response: Response,
    *,
    code_verifier: str,
    client_id: str,
    client_secret: str | None,
    resource: str | None,
    callback_url: str,
) -> None:
    payload = base64.urlsafe_b64encode(
        json.dumps(
            {
                "code_verifier": code_verifier,
                "client_id": client_id,
                "client_secret": client_secret,
                "resource": resource,
            },
            separators=(",", ":"),
        ).encode()
    ).decode()
    response.set_cookie(
        _NOTION_CONTEXT_COOKIE,
        payload,
        max_age=_PKCE_COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=callback_url.startswith("https"),
    )


def _parse_notion_context_cookie(value: str) -> dict[str, str | None]:
    try:
        decoded = base64.urlsafe_b64decode(value.encode()).decode()
        payload = json.loads(decoded)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=400, detail="Invalid Notion OAuth context"
        ) from exc

    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid Notion OAuth context")

    code_verifier = payload.get("code_verifier")
    client_id = payload.get("client_id")
    client_secret = payload.get("client_secret")
    resource = payload.get("resource")
    if not isinstance(code_verifier, str) or not isinstance(client_id, str):
        raise HTTPException(status_code=400, detail="Invalid Notion OAuth context")
    if client_secret is not None and not isinstance(client_secret, str):
        raise HTTPException(status_code=400, detail="Invalid Notion OAuth context")
    if resource is not None and not isinstance(resource, str):
        raise HTTPException(status_code=400, detail="Invalid Notion OAuth context")
    return {
        "code_verifier": code_verifier,
        "client_id": client_id,
        "client_secret": client_secret,
        "resource": resource,
    }


@router.get("")
async def list_connections(
    user: CurrentUserDep,
    services: ServicesDep,
    server_id: str = Query(...),
) -> list[dict[str, str | None]]:
    server = await _get_owned_server(services, server_id, user)
    connections = await services.store.list_connections(server.id)
    return [
        _serialize_connection(connection, services.credential_cipher)
        for connection in connections
    ]


@router.get("/{provider}/authorize", response_model=None)
async def authorize_connection(
    provider: str,
    request: Request,
    user: CurrentUserDep,
    services: ServicesDep,
    server_id: str = Query(...),
    response_mode: str | None = Query(None),
) -> Response:
    _, auth_type = _require_provider(provider)
    if auth_type != "oauth2":
        raise HTTPException(status_code=400, detail="Provider does not use OAuth")
    await _get_owned_server(services, server_id, user)
    callback_url = _resolve_callback_url(request, services)
    state = services.oauth_service.build_state(
        provider=provider,
        server_id=server_id,
        user_id=user.id,
    )

    if _provider_uses_hosted_mcp_oauth(provider):
        try:
            notion_authorization = await prepare_notion_mcp_authorization(
                state=state,
                redirect_uri=callback_url,
                client_name="Pixie",
                client_uri=_resolve_settings_url(request, services),
            )
        except OAuthProviderError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        notion_response: Response
        if response_mode == "json":
            notion_response = JSONResponse(
                {"authorize_url": notion_authorization.authorize_url}
            )
        else:
            notion_response = RedirectResponse(
                notion_authorization.authorize_url,
                status_code=302,
            )
        _set_notion_context_cookie(
            notion_response,
            code_verifier=notion_authorization.code_verifier,
            client_id=notion_authorization.client_id,
            client_secret=notion_authorization.client_secret,
            resource=notion_authorization.resource,
            callback_url=callback_url,
        )
        return notion_response

    try:
        authorize_url = services.oauth_service.get_authorize_url(
            provider,
            state,
            redirect_uri=callback_url,
            code_challenge=None,
        )
    except OAuthProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    if response_mode == "json":
        return JSONResponse({"authorize_url": authorize_url})
    return RedirectResponse(authorize_url, status_code=302)


@router.get("/oauth/callback")
async def oauth_callback(
    code: str,
    state: str,
    request: Request,
    services: ServicesDep,
    provider: str | None = None,
    notion_context: Annotated[str | None, Cookie(alias=_NOTION_CONTEXT_COOKIE)] = None,
) -> RedirectResponse:
    try:
        parsed_state = services.oauth_service.parse_state(state)
    except InvalidOAuthStateError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if provider is not None and provider != parsed_state.provider:
        raise HTTPException(
            status_code=400, detail="Provider does not match OAuth state"
        )

    server = await services.store.get_server_by_discord_id(parsed_state.server_id)
    if server is None:
        raise HTTPException(status_code=404, detail="Server is not claimed")
    if server.owner_user_id != parsed_state.user_id:
        raise HTTPException(status_code=403, detail="Not authorized for this server")

    if _provider_uses_hosted_mcp_oauth(parsed_state.provider):
        if notion_context is None:
            raise HTTPException(status_code=400, detail="Missing Notion OAuth context")
        notion_oauth_context = _parse_notion_context_cookie(notion_context)
        try:
            token_payload, scopes = await exchange_notion_mcp_code(
                code=code,
                redirect_uri=_resolve_callback_url(request, services),
                code_verifier=str(notion_oauth_context["code_verifier"]),
                client_id=str(notion_oauth_context["client_id"]),
                client_secret=(
                    str(notion_oauth_context["client_secret"])
                    if notion_oauth_context["client_secret"] is not None
                    else None
                ),
                resource=(
                    str(notion_oauth_context["resource"])
                    if notion_oauth_context["resource"] is not None
                    else None
                ),
            )
        except OAuthProviderError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        token_payload["oauth_client_id"] = str(notion_oauth_context["client_id"])
        if notion_oauth_context["client_secret"] is not None:
            token_payload["oauth_client_secret"] = str(
                notion_oauth_context["client_secret"]
            )
        if notion_oauth_context["resource"] is not None:
            token_payload["oauth_resource"] = str(notion_oauth_context["resource"])
    else:
        try:
            token_payload, scopes = await services.oauth_service.exchange_code(
                parsed_state.provider,
                code,
                redirect_uri=_resolve_callback_url(request, services),
                code_verifier=None,
            )
        except OAuthProviderError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    encrypted = services.credential_cipher.encrypt_credentials(token_payload)
    await services.store.upsert_connection(
        server.id,
        parsed_state.provider,
        encrypted,
        scopes,
        "active",
    )

    redirect_base_url = _resolve_settings_url(request, services)
    redirect_url = (
        f"{redirect_base_url}/settings"
        f"?server_id={parsed_state.server_id}&connected={parsed_state.provider}"
    )
    response = RedirectResponse(redirect_url, status_code=302)
    if notion_context is not None:
        response.delete_cookie(_NOTION_CONTEXT_COOKIE)
    return response


@router.post("/{provider}")
async def save_api_key_connection(
    provider: str,
    credentials: CredentialsBody,
    user: CurrentUserDep,
    services: ServicesDep,
    server_id: str = Query(...),
) -> dict[str, str | None]:
    _, auth_type = _require_provider(provider)
    if auth_type != "api_key":
        raise HTTPException(status_code=400, detail="Provider does not use API keys")
    server = await _get_owned_server(services, server_id, user)

    try:
        await services.api_key_validator.validate(provider, credentials)
    except InvalidApiKeyCredentialsError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    encrypted = services.credential_cipher.encrypt_credentials(credentials)
    connection = await services.store.upsert_connection(
        server.id,
        provider,
        encrypted,
        None,
        "active",
    )
    return _serialize_connection(connection, services.credential_cipher)


@router.delete("/{provider}")
async def disconnect_connection(
    provider: str,
    user: CurrentUserDep,
    services: ServicesDep,
    server_id: str = Query(...),
) -> Response:
    _require_provider(provider)
    server = await _get_owned_server(services, server_id, user)
    await services.store.delete_connection(server.id, provider)
    return Response(status_code=204)


@router.post("/{provider}/test")
async def test_connection(
    provider: str,
    user: CurrentUserDep,
    services: ServicesDep,
    server_id: str = Query(...),
) -> dict[str, bool]:
    _, auth_type = _require_provider(provider)
    server = await _get_owned_server(services, server_id, user)
    connection = await services.store.get_connection(server.id, provider)
    if connection is None:
        raise HTTPException(status_code=404, detail="Connection not found")
    if auth_type == "api_key":
        credentials = services.credential_cipher.decrypt_credentials(
            connection.credentials_encrypted
        )
        try:
            await services.api_key_validator.validate(provider, credentials)
        except InvalidApiKeyCredentialsError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"ok": True}
