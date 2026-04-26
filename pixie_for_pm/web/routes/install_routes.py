from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse

from pixie_for_pm.discord.install import build_bot_install_url
from pixie_for_pm.web.dependencies import ServicesDep

router = APIRouter(prefix="/api/discord", tags=["discord"])


@router.get("/install")
async def install_discord_bot(services: ServicesDep) -> RedirectResponse:
    application_id = services.settings.discord_application_id
    if application_id is None:
        raise HTTPException(
            status_code=503,
            detail="Discord bot installation is not configured on this server.",
        )

    return RedirectResponse(
        build_bot_install_url(
            application_id,
            permissions=services.settings.discord_install_permissions,
        ),
        status_code=302,
    )
