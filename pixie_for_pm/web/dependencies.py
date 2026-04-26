from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Annotated, cast

from fastapi import Depends, Request

from pixie_for_pm.config.settings import AppSettings

if TYPE_CHECKING:
    from pixie_for_pm.web.encryption import CredentialCipher
    from pixie_for_pm.web.providers.api_key import ApiKeyValidator
    from pixie_for_pm.web.providers.discord_login import DiscordLoginService
    from pixie_for_pm.web.providers.oauth import OAuthService
    from pixie_for_pm.web.session import SessionCodec
    from pixie_for_pm.web.store import ConnectionStore


@dataclass(frozen=True)
class WebAppServices:
    settings: AppSettings
    store: ConnectionStore
    discord_login_service: DiscordLoginService
    session_codec: SessionCodec
    api_key_validator: ApiKeyValidator
    oauth_service: OAuthService
    credential_cipher: CredentialCipher


def get_services(request: Request) -> WebAppServices:
    return cast(WebAppServices, request.app.state.services)


ServicesDep = Annotated[WebAppServices, Depends(get_services)]
