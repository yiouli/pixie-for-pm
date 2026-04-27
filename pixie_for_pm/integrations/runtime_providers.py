from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Protocol
from urllib.parse import quote, urlparse

import httpx
from langchain_core.tools import BaseTool, StructuredTool
from langchain_mcp_adapters.sessions import StreamableHttpConnection
from langchain_mcp_adapters.tools import load_mcp_tools
from pydantic import BaseModel, Field

from pixie_for_pm.integrations.toolset import (
    DiscordTriggerContext,
    IntegrationRuntimeProvider,
)
from pixie_for_pm.web.providers.oauth import (
    refresh_notion_mcp_token,
    refresh_vercel_mcp_token,
)


class SearchInput(BaseModel):
    query: str = Field(min_length=1)


class TranscriptLookupInput(BaseModel):
    transcript_id: str = Field(min_length=1)


class BaseListInput(BaseModel):
    workspace_id: str | None = None


class RecordQueryInput(BaseModel):
    base_id: str = Field(min_length=1)
    table_name: str = Field(min_length=1)
    formula: str | None = None


class McpToolLoader(Protocol):
    async def __call__(
        self,
        session: object | None,
        **kwargs: object,
    ) -> Sequence[BaseTool]: ...


class McpTokenRefresher(Protocol):
    async def __call__(
        self,
        credentials: Mapping[str, str],
    ) -> tuple[dict[str, str], list[str] | None]: ...


class HostedMcpToolProvider(IntegrationRuntimeProvider):
    def __init__(
        self,
        *,
        provider_id: str,
        server_url: str,
        token_field: str,
        resolve_url: (
            Callable[[Mapping[str, str], DiscordTriggerContext], str] | None
        ) = None,
        tool_loader: McpToolLoader | None = None,
        token_refresher: McpTokenRefresher | None = None,
    ) -> None:
        self._provider_id = provider_id
        self._server_url = server_url
        self._token_field = token_field
        self._resolve_url = resolve_url or (lambda _credentials, _trigger: server_url)
        self._tool_loader = tool_loader or load_mcp_tools
        self._token_refresher = token_refresher

    async def load_tools(
        self,
        *,
        credentials: Mapping[str, str],
        trigger: DiscordTriggerContext,
    ) -> tuple[BaseTool, ...]:
        token = credentials.get(self._token_field)
        if token is None or token.strip() == "":
            raise RuntimeError(
                f"Missing {self._token_field} for hosted MCP provider {self._provider_id}."
            )

        connection: StreamableHttpConnection = {
            "transport": "streamable_http",
            "url": self._resolve_url(credentials, trigger),
            "headers": {"Authorization": f"Bearer {token}"},
        }
        try:
            tools = await self._tool_loader(
                None,
                connection=connection,
                server_name=self._provider_id,
                tool_name_prefix=True,
            )
        except Exception as exc:
            if not _is_unauthorized_error(exc) or self._token_refresher is None:
                raise
            refreshed_credentials = await self._refresh_credentials(credentials)
            if isinstance(credentials, dict):
                credentials.clear()
                credentials.update(refreshed_credentials)
            connection = {
                "transport": "streamable_http",
                "url": self._resolve_url(refreshed_credentials, trigger),
                "headers": {
                    "Authorization": (
                        f"Bearer {refreshed_credentials[self._token_field]}"
                    )
                },
            }
            tools = await self._tool_loader(
                None,
                connection=connection,
                server_name=self._provider_id,
                tool_name_prefix=True,
            )
        return tuple(tools)

    async def _refresh_credentials(
        self,
        credentials: Mapping[str, str],
    ) -> dict[str, str]:
        refresh_token = credentials.get("refresh_token")
        client_id = credentials.get("oauth_client_id")
        resource = credentials.get("oauth_resource")
        if (
            refresh_token is None
            or refresh_token.strip() == ""
            or client_id is None
            or client_id.strip() == ""
            or resource is None
            or resource.strip() == ""
        ):
            provider_name = self._provider_id.capitalize()
            raise RuntimeError(
                f"Reconnect {provider_name} in Settings. Stored credentials were created "
                "before hosted MCP OAuth support and cannot be refreshed."
            )

        token_refresher = self._token_refresher
        if token_refresher is None:
            raise RuntimeError("Hosted MCP token refresher is not configured.")

        refreshed_payload, _ = await token_refresher(credentials)
        refreshed_credentials = dict(credentials)
        refreshed_credentials.update(refreshed_payload)
        refreshed_credentials.setdefault("refresh_token", refresh_token)
        refreshed_credentials.setdefault("oauth_client_id", client_id)
        refreshed_credentials.setdefault("oauth_resource", resource)
        client_secret = credentials.get("oauth_client_secret")
        if client_secret is not None and client_secret.strip() != "":
            refreshed_credentials.setdefault("oauth_client_secret", client_secret)
        return refreshed_credentials


class AirtableToolProvider(IntegrationRuntimeProvider):
    def __init__(self, *, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport

    async def load_tools(
        self,
        *,
        credentials: Mapping[str, str],
        trigger: DiscordTriggerContext,
    ) -> tuple[BaseTool, ...]:
        del trigger

        async def _list_bases(workspace_id: str | None = None) -> object:
            payload = await self._get_json(
                "https://api.airtable.com/v0/meta/bases",
                credentials=credentials,
            )
            bases = _expect_list(payload.get("bases"), "Airtable bases response")
            if workspace_id is None:
                return bases
            return [
                base
                for base in bases
                if isinstance(base, dict) and base.get("workspaceId") == workspace_id
            ]

        async def _query_records(
            base_id: str,
            table_name: str,
            formula: str | None = None,
        ) -> object:
            params = {"filterByFormula": formula} if formula is not None else None
            table_path = quote(table_name, safe="")
            return await self._get_json(
                f"https://api.airtable.com/v0/{base_id}/{table_path}",
                credentials=credentials,
                params=params,
            )

        return (
            StructuredTool.from_function(
                coroutine=_list_bases,
                name="airtable_list_bases",
                description="List Airtable bases available to the connected workspace.",
                args_schema=BaseListInput,
            ),
            StructuredTool.from_function(
                coroutine=_query_records,
                name="airtable_query_records",
                description="Query Airtable records from a specific base and table.",
                args_schema=RecordQueryInput,
            ),
        )

    async def _get_json(
        self,
        url: str,
        *,
        credentials: Mapping[str, str],
        params: Mapping[str, str] | None = None,
    ) -> dict[str, object]:
        token = credentials.get("access_token")
        if token is None or token.strip() == "":
            raise RuntimeError("Missing access_token for Airtable connection.")

        try:
            async with httpx.AsyncClient(
                transport=self._transport,
                timeout=15.0,
            ) as client:
                response = await client.get(
                    url,
                    headers={"Authorization": f"Bearer {token}"},
                    params=params,
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise RuntimeError("Airtable request failed.") from exc

        return _expect_dict(response.json(), "Airtable response")


class FirefliesToolProvider(IntegrationRuntimeProvider):
    def __init__(self, *, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport

    async def load_tools(
        self,
        *,
        credentials: Mapping[str, str],
        trigger: DiscordTriggerContext,
    ) -> tuple[BaseTool, ...]:
        del trigger

        async def _get_transcript(transcript_id: str) -> object:
            data = await self._query_graphql(
                credentials=credentials,
                operation_name="GetTranscript",
                query="""
                query GetTranscript($transcriptId: String!) {
                  transcript(id: $transcriptId) {
                    id
                    title
                    date
                    transcript_url
                    duration
                    summary {
                      gist
                      short_summary
                      short_overview
                      action_items
                    }
                  }
                }
                """,
                variables={"transcriptId": transcript_id},
            )
            return _expect_dict(data.get("transcript"), "Fireflies transcript")

        async def _search_transcripts(query: str) -> object:
            data = await self._query_graphql(
                credentials=credentials,
                operation_name="SearchTranscripts",
                query="""
                query SearchTranscripts($query: String!) {
                  transcripts(keyword: $query, limit: 10) {
                    id
                    title
                    date
                    transcript_url
                    duration
                    summary {
                      gist
                      short_summary
                    }
                  }
                }
                """,
                variables={"query": query},
            )
            return _expect_list(data.get("transcripts"), "Fireflies transcripts")

        return (
            StructuredTool.from_function(
                coroutine=_get_transcript,
                name="fireflies_get_transcript",
                description="Fetch a Fireflies transcript by transcript ID.",
                args_schema=TranscriptLookupInput,
            ),
            StructuredTool.from_function(
                coroutine=_search_transcripts,
                name="fireflies_search_transcripts",
                description="Search Fireflies transcripts using a free-text query.",
                args_schema=SearchInput,
            ),
        )

    async def _query_graphql(
        self,
        *,
        credentials: Mapping[str, str],
        operation_name: str,
        query: str,
        variables: dict[str, str],
    ) -> dict[str, object]:
        api_key = credentials.get("api_key")
        if api_key is None or api_key.strip() == "":
            raise RuntimeError("Missing api_key for Fireflies connection.")

        try:
            async with httpx.AsyncClient(
                transport=self._transport,
                timeout=15.0,
            ) as client:
                response = await client.post(
                    "https://api.fireflies.ai/graphql",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={
                        "operationName": operation_name,
                        "query": query,
                        "variables": variables,
                    },
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise RuntimeError("Fireflies request failed.") from exc

        payload = _expect_dict(response.json(), "Fireflies GraphQL response")
        errors = payload.get("errors")
        if errors is not None:
            raise RuntimeError("Fireflies GraphQL request returned errors.")
        return _expect_dict(payload.get("data"), "Fireflies GraphQL data")


def build_runtime_providers() -> dict[str, IntegrationRuntimeProvider]:
    return {
        "notion": HostedMcpToolProvider(
            provider_id="notion",
            server_url="https://mcp.notion.com/mcp",
            token_field="access_token",
            token_refresher=refresh_notion_mcp_token,
        ),
        "github": HostedMcpToolProvider(
            provider_id="github",
            server_url="https://api.githubcopilot.com/mcp/",
            token_field="access_token",
        ),
        "vercel": HostedMcpToolProvider(
            provider_id="vercel",
            server_url="https://mcp.vercel.com",
            token_field="access_token",
            token_refresher=refresh_vercel_mcp_token,
        ),
        "posthog": HostedMcpToolProvider(
            provider_id="posthog",
            server_url="https://mcp.posthog.com/mcp",
            token_field="api_key",
            resolve_url=_resolve_posthog_mcp_url,
        ),
        "airtable": AirtableToolProvider(),
        "fireflies": FirefliesToolProvider(),
    }


def _is_unauthorized_error(exc: Exception) -> bool:
    if isinstance(exc, BaseExceptionGroup):
        return any(
            isinstance(child, Exception) and _is_unauthorized_error(child)
            for child in exc.exceptions
        )
    if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 401:
        return True
    message = str(exc).lower()
    return "401" in message and "unauthorized" in message


def _resolve_posthog_mcp_url(
    credentials: Mapping[str, str],
    trigger: DiscordTriggerContext,
) -> str:
    del trigger
    host = credentials.get("host")
    if host is None:
        return "https://mcp.posthog.com/mcp"

    parsed = urlparse(host)
    if parsed.netloc.startswith("eu."):
        return "https://mcp-eu.posthog.com/mcp"
    return "https://mcp.posthog.com/mcp"


def _expect_dict(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise RuntimeError(f"Unexpected {label} payload.")
    return value


def _expect_list(value: object, label: str) -> list[object]:
    if not isinstance(value, list):
        raise RuntimeError(f"Unexpected {label} payload.")
    return value
