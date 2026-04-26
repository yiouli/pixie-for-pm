"""Fireflies credential access helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pixie_for_pm.integrations.credentials import get_credentials

if TYPE_CHECKING:
    from pixie_for_pm.web.encryption import CredentialCipher
    from pixie_for_pm.web.store import ConnectionStore


async def get_fireflies_credentials(
    discord_server_id: str,
    *,
    store: ConnectionStore,
    cipher: CredentialCipher,
) -> dict[str, str] | None:
    """Return decrypted Fireflies API key credentials for *discord_server_id*, or ``None``."""
    return await get_credentials(
        discord_server_id, "fireflies", store=store, cipher=cipher
    )
