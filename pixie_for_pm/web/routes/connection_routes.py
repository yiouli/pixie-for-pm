from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Body, HTTPException, Query, Response
from fastapi.responses import RedirectResponse

from pixie_for_pm.integrations.registry import PROVIDERS
from pixie_for_pm.web.auth import AuthenticatedUser, CurrentUserDep
from pixie_for_pm.web.dependencies import ServicesDep, WebAppServices
from pixie_for_pm.web.providers.api_key import InvalidApiKeyCredentialsError
from pixie_for_pm.web.providers.oauth import InvalidOAuthStateError, OAuthProviderError
from pixie_for_pm.web.store import ConnectionRecord, ServerRecord

router = APIRouter(prefix="/api/connections", tags=["connections"])

CredentialsBody = Annotated[dict[str, str], Body(...)]


def _format_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _serialize_connection(connection: ConnectionRecord) -> dict[str, str | None]:
    return {
        "provider": connection.provider,
        "status": connection.status,
        "connected_at": connection.connected_at.isoformat(),
        "last_used_at": _format_datetime(connection.last_used_at),
    }


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


@router.get("")
async def list_connections(
    user: CurrentUserDep,
    services: ServicesDep,
    server_id: str = Query(...),
) -> list[dict[str, str | None]]:
    server = await _get_owned_server(services, server_id, user)
    connections = await services.store.list_connections(server.id)
    return [_serialize_connection(connection) for connection in connections]


@router.get("/{provider}/authorize", response_model=None)
async def authorize_connection(
    provider: str,
    user: CurrentUserDep,
    services: ServicesDep,
    server_id: str = Query(...),
    response_mode: str | None = Query(None),
) -> RedirectResponse | dict[str, str]:
    _, auth_type = _require_provider(provider)
    if auth_type != "oauth2":
        raise HTTPException(status_code=400, detail="Provider does not use OAuth")
    await _get_owned_server(services, server_id, user)
    try:
        state = services.oauth_service.build_state(
            provider=provider,
            server_id=server_id,
            user_id=user.id,
        )
        authorize_url = services.oauth_service.get_authorize_url(provider, state)
    except OAuthProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if response_mode == "json":
        return {"authorize_url": authorize_url}
    return RedirectResponse(authorize_url, status_code=302)


@router.get("/oauth/callback")
async def oauth_callback(
    code: str,
    state: str,
    services: ServicesDep,
    provider: str | None = None,
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

    try:
        token_payload, scopes = await services.oauth_service.exchange_code(
            parsed_state.provider,
            code,
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

    if services.settings.web_app_url is None:
        raise HTTPException(status_code=503, detail="WEB_APP_URL is not configured")
    redirect_url = (
        f"{services.settings.web_app_url}/settings"
        f"?server_id={parsed_state.server_id}&connected={parsed_state.provider}"
    )
    return RedirectResponse(redirect_url, status_code=302)


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
    return _serialize_connection(connection)


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
