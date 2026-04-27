from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response, status

from pixie_for_pm.web.auth import CurrentUserDep
from pixie_for_pm.web.dependencies import ServicesDep
from pixie_for_pm.web.providers.discord_guilds import DiscordGuildLookupError
from pixie_for_pm.web.store import ServerOwnershipConflictError, ServerRecord

router = APIRouter(prefix="/api/servers", tags=["servers"])


def _serialize_server(
    server: ServerRecord,
    *,
    owned_by_current_user: bool,
) -> dict[str, str | bool | None]:
    return {
        "id": server.id,
        "discord_server_id": server.discord_server_id,
        "icon_url": server.icon_url,
        "name": server.name,
        "owned_by_current_user": owned_by_current_user,
    }


@router.get("/{discord_server_id}")
async def get_server(
    discord_server_id: str,
    user: CurrentUserDep,
    services: ServicesDep,
) -> dict[str, str | bool | None]:
    server = await services.store.get_server_by_discord_id(discord_server_id)
    if server is None:
        raise HTTPException(status_code=404, detail="Server is not claimed")
    return _serialize_server(
        server,
        owned_by_current_user=server.owner_user_id == user.id,
    )


@router.post("/{discord_server_id}/claim")
async def claim_server(
    discord_server_id: str,
    user: CurrentUserDep,
    services: ServicesDep,
    response: Response,
) -> dict[str, str | bool | None]:
    guild = None
    try:
        guild = await services.discord_guild_service.get_guild(discord_server_id)
    except DiscordGuildLookupError:
        guild = None

    try:
        server, created = await services.store.claim_server(
            discord_server_id,
            user.id,
            name=guild.name if guild is not None else None,
            icon_url=guild.icon_url if guild is not None else None,
        )
    except ServerOwnershipConflictError as exc:
        raise HTTPException(status_code=409, detail="Server is already owned") from exc

    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return _serialize_server(server, owned_by_current_user=True)


@router.get("")
async def list_servers(
    user: CurrentUserDep,
    services: ServicesDep,
) -> list[dict[str, str | bool | None]]:
    servers = await services.store.list_servers_for_owner(user.id)
    return [_serialize_server(server, owned_by_current_user=True) for server in servers]
