from __future__ import annotations

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol, cast
from uuid import uuid4

from supabase import Client, create_client

from pixie_for_pm.config.settings import AppSettings


@dataclass(frozen=True)
class ServerRecord:
    id: str
    discord_server_id: str
    owner_user_id: str
    name: str | None
    created_at: datetime


@dataclass(frozen=True)
class ConnectionRecord:
    id: str
    server_id: str
    provider: str
    credentials_encrypted: str
    scopes: list[str] | None
    status: str
    connected_at: datetime
    last_used_at: datetime | None


class ServerOwnershipConflictError(Exception):
    """Raised when a different user already owns the requested server."""


class ConnectionStore(Protocol):
    async def get_server_by_discord_id(
        self, discord_server_id: str
    ) -> ServerRecord | None: ...

    async def claim_server(
        self,
        discord_server_id: str,
        owner_user_id: str,
        name: str | None = None,
    ) -> tuple[ServerRecord, bool]: ...

    async def list_servers_for_owner(
        self, owner_user_id: str
    ) -> list[ServerRecord]: ...

    async def get_connection(
        self, server_id: str, provider: str
    ) -> ConnectionRecord | None: ...

    async def get_connection_by_discord_server(
        self, discord_server_id: str, provider: str
    ) -> ConnectionRecord | None: ...

    async def list_connections(self, server_id: str) -> list[ConnectionRecord]: ...

    async def upsert_connection(
        self,
        server_id: str,
        provider: str,
        credentials_encrypted: str,
        scopes: list[str] | None,
        status: str,
    ) -> ConnectionRecord: ...

    async def delete_connection(self, server_id: str, provider: str) -> bool: ...

    async def touch_connection_last_used(
        self, server_id: str, provider: str
    ) -> None: ...


class InMemoryConnectionStore(ConnectionStore):
    def __init__(
        self,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._now = now or (lambda: datetime(2026, 1, 1, tzinfo=UTC))
        self._servers_by_discord_id: dict[str, ServerRecord] = {}
        self._connections_by_key: dict[tuple[str, str], ConnectionRecord] = {}
        self._server_sequence = 0
        self._connection_sequence = 0

    async def get_server_by_discord_id(
        self, discord_server_id: str
    ) -> ServerRecord | None:
        return self._servers_by_discord_id.get(discord_server_id)

    async def claim_server(
        self,
        discord_server_id: str,
        owner_user_id: str,
        name: str | None = None,
    ) -> tuple[ServerRecord, bool]:
        existing = self._servers_by_discord_id.get(discord_server_id)
        if existing is not None:
            if existing.owner_user_id != owner_user_id:
                raise ServerOwnershipConflictError(discord_server_id)
            updated = replace(
                existing, name=name if name is not None else existing.name
            )
            self._servers_by_discord_id[discord_server_id] = updated
            return updated, False

        self._server_sequence += 1
        created = ServerRecord(
            id=f"server-{self._server_sequence}",
            discord_server_id=discord_server_id,
            owner_user_id=owner_user_id,
            name=name,
            created_at=self._now(),
        )
        self._servers_by_discord_id[discord_server_id] = created
        return created, True

    async def list_servers_for_owner(self, owner_user_id: str) -> list[ServerRecord]:
        return sorted(
            (
                server
                for server in self._servers_by_discord_id.values()
                if server.owner_user_id == owner_user_id
            ),
            key=lambda server: server.discord_server_id,
        )

    async def get_connection(
        self, server_id: str, provider: str
    ) -> ConnectionRecord | None:
        return self._connections_by_key.get((server_id, provider))

    async def get_connection_by_discord_server(
        self, discord_server_id: str, provider: str
    ) -> ConnectionRecord | None:
        server = self._servers_by_discord_id.get(discord_server_id)
        if server is None:
            return None
        return self._connections_by_key.get((server.id, provider))

    async def list_connections(self, server_id: str) -> list[ConnectionRecord]:
        return sorted(
            (
                connection
                for connection in self._connections_by_key.values()
                if connection.server_id == server_id
            ),
            key=lambda connection: connection.provider,
        )

    async def upsert_connection(
        self,
        server_id: str,
        provider: str,
        credentials_encrypted: str,
        scopes: list[str] | None,
        status: str,
    ) -> ConnectionRecord:
        key = (server_id, provider)
        existing = self._connections_by_key.get(key)
        if existing is not None:
            updated = replace(
                existing,
                credentials_encrypted=credentials_encrypted,
                scopes=scopes,
                status=status,
                connected_at=self._now(),
            )
            self._connections_by_key[key] = updated
            return updated

        self._connection_sequence += 1
        created = ConnectionRecord(
            id=f"connection-{self._connection_sequence}",
            server_id=server_id,
            provider=provider,
            credentials_encrypted=credentials_encrypted,
            scopes=scopes,
            status=status,
            connected_at=self._now(),
            last_used_at=None,
        )
        self._connections_by_key[key] = created
        return created

    async def delete_connection(self, server_id: str, provider: str) -> bool:
        key = (server_id, provider)
        return self._connections_by_key.pop(key, None) is not None

    async def touch_connection_last_used(self, server_id: str, provider: str) -> None:
        key = (server_id, provider)
        existing = self._connections_by_key.get(key)
        if existing is None:
            return
        self._connections_by_key[key] = replace(existing, last_used_at=self._now())


class SQLiteConnectionStore(ConnectionStore):
    def __init__(self, database_path: Path) -> None:
        self._database_path = Path(database_path)
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                create table if not exists servers (
                  id text primary key,
                  discord_server_id text not null unique,
                  owner_user_id text not null,
                  name text,
                  created_at text not null
                );

                create table if not exists connections (
                  id text primary key,
                  server_id text not null,
                  provider text not null,
                  credentials_encrypted text not null,
                  scopes text,
                  status text not null,
                  connected_at text not null,
                  last_used_at text,
                  unique(server_id, provider)
                );
                """
            )

    async def get_server_by_discord_id(
        self, discord_server_id: str
    ) -> ServerRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                "select * from servers where discord_server_id = ? limit 1",
                (discord_server_id,),
            ).fetchone()
        if row is None:
            return None
        return _server_from_row(dict(row))

    async def claim_server(
        self,
        discord_server_id: str,
        owner_user_id: str,
        name: str | None = None,
    ) -> tuple[ServerRecord, bool]:
        existing = await self.get_server_by_discord_id(discord_server_id)
        if existing is not None:
            if existing.owner_user_id != owner_user_id:
                raise ServerOwnershipConflictError(discord_server_id)
            if name is not None and name != existing.name:
                with self._connect() as connection:
                    connection.execute(
                        "update servers set name = ? where discord_server_id = ?",
                        (name, discord_server_id),
                    )
                updated = await self.get_server_by_discord_id(discord_server_id)
                if updated is None:
                    raise RuntimeError("SQLite store lost the claimed server row.")
                return updated, False
            return existing, False

        created_at = datetime.now(tz=UTC).isoformat()
        server_id = str(uuid4())
        with self._connect() as connection:
            connection.execute(
                """
                insert into servers (
                                    id, discord_server_id, owner_user_id, name, created_at
                                ) values (?, ?, ?, ?, ?)
                """,
                (
                    server_id,
                    discord_server_id,
                    owner_user_id,
                    name,
                    created_at,
                ),
            )
        created = await self.get_server_by_discord_id(discord_server_id)
        if created is None:
            raise RuntimeError("SQLite store did not return the claimed server row.")
        return created, True

    async def list_servers_for_owner(self, owner_user_id: str) -> list[ServerRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                "select * from servers where owner_user_id = ? order by discord_server_id",
                (owner_user_id,),
            ).fetchall()
        return [_server_from_row(dict(row)) for row in rows]

    async def get_connection(
        self, server_id: str, provider: str
    ) -> ConnectionRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                "select * from connections where server_id = ? and provider = ? limit 1",
                (server_id, provider),
            ).fetchone()
        if row is None:
            return None
        return _connection_from_row(dict(row))

    async def get_connection_by_discord_server(
        self, discord_server_id: str, provider: str
    ) -> ConnectionRecord | None:
        server = await self.get_server_by_discord_id(discord_server_id)
        if server is None:
            return None
        return await self.get_connection(server.id, provider)

    async def list_connections(self, server_id: str) -> list[ConnectionRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                "select * from connections where server_id = ? order by provider",
                (server_id,),
            ).fetchall()
        return [_connection_from_row(dict(row)) for row in rows]

    async def upsert_connection(
        self,
        server_id: str,
        provider: str,
        credentials_encrypted: str,
        scopes: list[str] | None,
        status: str,
    ) -> ConnectionRecord:
        connection_id = str(uuid4())
        now = datetime.now(tz=UTC).isoformat()
        scopes_value = " ".join(scopes) if scopes is not None else None
        with self._connect() as connection:
            connection.execute(
                """
                insert into connections (
                  id, server_id, provider, credentials_encrypted,
                  scopes, status, connected_at, last_used_at
                ) values (?, ?, ?, ?, ?, ?, ?, null)
                on conflict(server_id, provider)
                do update set
                  credentials_encrypted = excluded.credentials_encrypted,
                  scopes = excluded.scopes,
                  status = excluded.status,
                  connected_at = excluded.connected_at
                """,
                (
                    connection_id,
                    server_id,
                    provider,
                    credentials_encrypted,
                    scopes_value,
                    status,
                    now,
                ),
            )
        updated = await self.get_connection(server_id, provider)
        if updated is None:
            raise RuntimeError("SQLite store did not return the connection row.")
        return updated

    async def delete_connection(self, server_id: str, provider: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "delete from connections where server_id = ? and provider = ?",
                (server_id, provider),
            )
            return cursor.rowcount > 0

    async def touch_connection_last_used(self, server_id: str, provider: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                update connections
                set last_used_at = ?
                where server_id = ? and provider = ?
                """,
                (datetime.now(tz=UTC).isoformat(), server_id, provider),
            )


class SupabaseConnectionStore(ConnectionStore):
    def __init__(self, supabase_url: str, service_role_key: str) -> None:
        self._client: Client = create_client(supabase_url, service_role_key)

    async def get_server_by_discord_id(
        self, discord_server_id: str
    ) -> ServerRecord | None:
        response = (
            self._client.table("servers")
            .select("*")
            .eq("discord_server_id", discord_server_id)
            .limit(1)
            .execute()
        )
        rows = _response_rows(response)
        if not rows:
            return None
        return _server_from_row(rows[0])

    async def claim_server(
        self,
        discord_server_id: str,
        owner_user_id: str,
        name: str | None = None,
    ) -> tuple[ServerRecord, bool]:
        existing = await self.get_server_by_discord_id(discord_server_id)
        if existing is not None:
            if existing.owner_user_id != owner_user_id:
                raise ServerOwnershipConflictError(discord_server_id)
            next_name = name if name is not None else existing.name
            if next_name != existing.name:
                response = (
                    self._client.table("servers")
                    .update({"name": next_name})
                    .eq("id", existing.id)
                    .execute()
                )
                rows = _response_rows(response)
                if rows:
                    return _server_from_row(rows[0]), False
                refreshed = await self.get_server_by_discord_id(discord_server_id)
                if refreshed is None:
                    raise RuntimeError("Supabase lost the claimed server row.")
                return refreshed, False
            return existing, False

        response = (
            self._client.table("servers")
            .insert(
                {
                    "discord_server_id": discord_server_id,
                    "owner_user_id": owner_user_id,
                    "name": name,
                }
            )
            .execute()
        )
        rows = _response_rows(response)
        if not rows:
            raise RuntimeError("Supabase did not return the claimed server row.")
        return _server_from_row(rows[0]), True

    async def list_servers_for_owner(self, owner_user_id: str) -> list[ServerRecord]:
        response = (
            self._client.table("servers")
            .select("*")
            .eq("owner_user_id", owner_user_id)
            .order("discord_server_id")
            .execute()
        )
        return [_server_from_row(row) for row in _response_rows(response)]

    async def get_connection(
        self, server_id: str, provider: str
    ) -> ConnectionRecord | None:
        response = (
            self._client.table("connections")
            .select("*")
            .eq("server_id", server_id)
            .eq("provider", provider)
            .limit(1)
            .execute()
        )
        rows = _response_rows(response)
        if not rows:
            return None
        return _connection_from_row(rows[0])

    async def get_connection_by_discord_server(
        self, discord_server_id: str, provider: str
    ) -> ConnectionRecord | None:
        server = await self.get_server_by_discord_id(discord_server_id)
        if server is None:
            return None
        return await self.get_connection(server.id, provider)

    async def list_connections(self, server_id: str) -> list[ConnectionRecord]:
        response = (
            self._client.table("connections")
            .select("*")
            .eq("server_id", server_id)
            .order("provider")
            .execute()
        )
        return [_connection_from_row(row) for row in _response_rows(response)]

    async def upsert_connection(
        self,
        server_id: str,
        provider: str,
        credentials_encrypted: str,
        scopes: list[str] | None,
        status: str,
    ) -> ConnectionRecord:
        response = (
            self._client.table("connections")
            .upsert(
                {
                    "server_id": server_id,
                    "provider": provider,
                    "credentials_encrypted": credentials_encrypted,
                    "scopes": scopes,
                    "status": status,
                },
                on_conflict="server_id,provider",
            )
            .execute()
        )
        rows = _response_rows(response)
        if not rows:
            updated = await self.get_connection(server_id, provider)
            if updated is None:
                raise RuntimeError("Supabase did not return the connection row.")
            return updated
        return _connection_from_row(rows[0])

    async def delete_connection(self, server_id: str, provider: str) -> bool:
        response = (
            self._client.table("connections")
            .delete()
            .eq("server_id", server_id)
            .eq("provider", provider)
            .execute()
        )
        return bool(_response_rows(response))

    async def touch_connection_last_used(self, server_id: str, provider: str) -> None:
        self._client.table("connections").update(
            {"last_used_at": datetime.now(tz=UTC).isoformat()}
        ).eq("server_id", server_id).eq("provider", provider).execute()


def _response_rows(response: object) -> list[dict[str, object]]:
    data = getattr(response, "data", None)
    if isinstance(data, list):
        return [cast(dict[str, object], row) for row in data if isinstance(row, dict)]
    if isinstance(data, dict):
        return [cast(dict[str, object], data)]
    return []


def _server_from_row(row: dict[str, object]) -> ServerRecord:
    return ServerRecord(
        id=str(row["id"]),
        discord_server_id=str(row["discord_server_id"]),
        owner_user_id=str(row["owner_user_id"]),
        name=_optional_text(row.get("name")),
        created_at=_parse_datetime(row.get("created_at")),
    )


def _connection_from_row(row: dict[str, object]) -> ConnectionRecord:
    scopes_value = row.get("scopes")
    scopes: list[str] | None = None
    if isinstance(scopes_value, list):
        scopes = [str(value) for value in scopes_value]
    elif isinstance(scopes_value, str) and scopes_value != "":
        scopes = [scope for scope in scopes_value.split(" ") if scope]

    last_used_value = row.get("last_used_at")
    last_used_at = (
        _parse_datetime(last_used_value) if last_used_value is not None else None
    )

    return ConnectionRecord(
        id=str(row["id"]),
        server_id=str(row["server_id"]),
        provider=str(row["provider"]),
        credentials_encrypted=str(row["credentials_encrypted"]),
        scopes=scopes,
        status=str(row["status"]),
        connected_at=_parse_datetime(row.get("connected_at")),
        last_used_at=last_used_at,
    )


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _parse_datetime(value: object) -> datetime:
    if value is None:
        raise ValueError("Expected a timestamp value from Supabase.")
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def build_connection_store(settings: AppSettings) -> ConnectionStore:
    if settings.supabase_url and settings.supabase_service_role_key:
        return SupabaseConnectionStore(
            settings.supabase_url,
            settings.supabase_service_role_key,
        )
    return SQLiteConnectionStore(settings.connection_store_sqlite_path)
