import pytest

from pixie_for_pm.integrations.credentials import get_credentials
from pixie_for_pm.web.encryption import CredentialCipher
from pixie_for_pm.web.store import InMemoryConnectionStore

_FERNET_KEY = "j0aN3s-cLScfv0GfNyG8t0UyONn7y8u2s6o6cLs1hYw="


@pytest.mark.asyncio
async def test_get_credentials_returns_decrypted_payload_from_store() -> None:
    store = InMemoryConnectionStore()
    cipher = CredentialCipher(_FERNET_KEY)

    # Seed the store via the claim → upsert path
    await store.claim_server("server-123", "user-1")
    server = await store.get_server_by_discord_id("server-123")
    assert server is not None
    await store.upsert_connection(
        server.id,
        "notion",
        cipher.encrypt_credentials({"access_token": "notion-token"}),
        scopes=["read"],
        status="active",
    )

    result = await get_credentials("server-123", "notion", store=store, cipher=cipher)

    assert result == {"access_token": "notion-token"}


@pytest.mark.asyncio
async def test_get_credentials_returns_none_when_provider_not_connected() -> None:
    store = InMemoryConnectionStore()
    cipher = CredentialCipher(_FERNET_KEY)

    await store.claim_server("server-456", "user-1")

    result = await get_credentials("server-456", "notion", store=store, cipher=cipher)

    assert result is None


@pytest.mark.asyncio
async def test_get_credentials_returns_none_for_unknown_server() -> None:
    store = InMemoryConnectionStore()
    cipher = CredentialCipher(_FERNET_KEY)

    result = await get_credentials(
        "no-such-server", "notion", store=store, cipher=cipher
    )

    assert result is None
