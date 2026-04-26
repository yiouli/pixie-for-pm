from pathlib import Path

import pytest

from pixie_for_pm.web.store import SQLiteConnectionStore


@pytest.mark.asyncio
async def test_sqlite_store_shares_server_state_across_instances(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "pixie-store.sqlite"
    writer = SQLiteConnectionStore(database_path)
    reader = SQLiteConnectionStore(database_path)

    await writer.claim_server("server-123", "user-1")

    server = await reader.get_server_by_discord_id("server-123")

    assert server is not None
    assert server.discord_server_id == "server-123"
