"""Integration credential accessor.

Agents call :func:`get_credentials` to retrieve the decrypted credentials for
a given Discord server and integration provider.

Design
------
Credentials are stored encrypted in the :class:`~pixie_for_pm.web.store.ConnectionStore`
(Supabase or in-memory) and decrypted on-demand with
:class:`~pixie_for_pm.web.encryption.CredentialCipher`.  Because the Discord
bot and the settings web server share the same Python codebase, there is no
HTTP hop — the agent runtime holds direct references to the store and cipher
instances and calls this function inline.

This keeps plaintext credentials out of any network transport and avoids the
need for a shared internal API key.

Usage
-----
The agent container (Discord bot, LangGraph runtime) must construct and inject
``store`` and ``cipher`` at startup::

    from pixie_for_pm.web.store import SupabaseConnectionStore
    from pixie_for_pm.web.encryption import CredentialCipher

    store = SupabaseConnectionStore(settings.supabase_url, settings.supabase_service_role_key)
    cipher = CredentialCipher(settings.credentials_encryption_key)

    creds = await get_credentials("discord-server-id", "notion", store=store, cipher=cipher)
    if creds is not None:
        notion_token = creds["access_token"]
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pixie_for_pm.web.encryption import CredentialCipher
    from pixie_for_pm.web.store import ConnectionStore


async def get_credentials(
    discord_server_id: str,
    provider: str,
    *,
    store: ConnectionStore,
    cipher: CredentialCipher,
) -> dict[str, str] | None:
    """Return decrypted credentials for *provider* on *discord_server_id*.

    Returns ``None`` when the server has not connected the requested provider.

    Args:
        discord_server_id: The Discord guild snowflake ID (as a string).
        provider: Provider slug (e.g. ``"notion"``, ``"github"``).
        store: The connection store containing the encrypted credential records.
        cipher: The cipher used to decrypt stored credentials.
    """
    connection = await store.get_connection_by_discord_server(
        discord_server_id, provider
    )
    if connection is None:
        return None
    return cipher.decrypt_credentials(connection.credentials_encrypted)
