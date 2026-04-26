"""Airtable credential access helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pixie_for_pm.integrations.credentials import get_credentials

if TYPE_CHECKING:
    from pixie_for_pm.web.encryption import CredentialCipher
    from pixie_for_pm.web.store import ConnectionStore


async def get_airtable_credentials(
    discord_server_id: str,
    *,
    store: ConnectionStore,
    cipher: CredentialCipher,
) -> dict[str, str] | None:
    """Return decrypted Airtable OAuth credentials for *discord_server_id*, or ``None``."""
    return await get_credentials(
        discord_server_id, "airtable", store=store, cipher=cipher
    )
