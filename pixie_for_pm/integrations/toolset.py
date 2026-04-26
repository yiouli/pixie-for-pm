from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, Protocol

from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, Field

from pixie_for_pm.config.settings import AppSettings
from pixie_for_pm.integrations.registry import PROVIDERS
from pixie_for_pm.web.encryption import CredentialCipher
from pixie_for_pm.web.store import build_connection_store

if TYPE_CHECKING:
    from pixie_for_pm.web.store import ConnectionStore


@dataclass(frozen=True)
class DiscordTriggerContext:
    discord_server_id: str
    discord_user_id: str
    channel_id: int
    thread_id: str | None
    message_id: int
    thread_key: str
    dispatch_reason: str


@dataclass(frozen=True)
class ConnectedIntegration:
    provider_id: str
    provider_name: str
    auth_type: Literal["oauth2", "api_key"]
    status: str
    scopes: tuple[str, ...]
    tool_names: tuple[str, ...]


@dataclass(frozen=True)
class AgentToolset:
    tools: tuple[BaseTool, ...] = ()
    integrations: tuple[ConnectedIntegration, ...] = ()

    def as_langgraph_tools(self) -> tuple[BaseTool, ...]:
        return self.tools


@dataclass(frozen=True)
class IntegrationToolCall:
    provider_id: str
    tool_name: str
    arguments: dict[str, object]
    credentials: dict[str, str]
    trigger: DiscordTriggerContext


class McpToolInvoker(Protocol):
    async def invoke(self, call: IntegrationToolCall) -> object: ...


class ToolsetInitializer(Protocol):
    async def initialize(self, trigger: DiscordTriggerContext) -> AgentToolset: ...


class EmptyToolsetInitializer:
    async def initialize(self, trigger: DiscordTriggerContext) -> AgentToolset:
        del trigger
        return AgentToolset()


class MissingMcpToolInvoker:
    async def invoke(self, call: IntegrationToolCall) -> object:
        raise RuntimeError(
            "No MCP tool invoker is configured for "
            f"{call.provider_id}.{call.tool_name}."
        )


class SearchInput(BaseModel):
    query: str = Field(min_length=1)


class PageLookupInput(BaseModel):
    page_id: str = Field(min_length=1)


class IssueSearchInput(BaseModel):
    query: str = Field(min_length=1)


class IssueCreateInput(BaseModel):
    repository: str = Field(min_length=1)
    title: str = Field(min_length=1)
    body: str | None = None


class ProjectListInput(BaseModel):
    team_id: str | None = None


class DeploymentLookupInput(BaseModel):
    deployment_id: str = Field(min_length=1)


class BaseListInput(BaseModel):
    workspace_id: str | None = None


class RecordQueryInput(BaseModel):
    base_id: str = Field(min_length=1)
    table_name: str = Field(min_length=1)
    formula: str | None = None


class InsightQueryInput(BaseModel):
    query: str = Field(min_length=1)


class FeatureFlagLookupInput(BaseModel):
    key: str = Field(min_length=1)


class TranscriptLookupInput(BaseModel):
    transcript_id: str = Field(min_length=1)


@dataclass(frozen=True)
class ProviderToolDefinition:
    provider_id: str
    name: str
    description: str
    args_schema: type[BaseModel]


PROVIDER_TOOL_CATALOG: dict[str, tuple[ProviderToolDefinition, ...]] = {
    "airtable": (
        ProviderToolDefinition(
            provider_id="airtable",
            name="airtable_list_bases",
            description="List Airtable bases available to the connected workspace.",
            args_schema=BaseListInput,
        ),
        ProviderToolDefinition(
            provider_id="airtable",
            name="airtable_query_records",
            description="Query Airtable records from a specific base and table.",
            args_schema=RecordQueryInput,
        ),
    ),
    "fireflies": (
        ProviderToolDefinition(
            provider_id="fireflies",
            name="fireflies_get_transcript",
            description="Fetch a Fireflies transcript by transcript ID.",
            args_schema=TranscriptLookupInput,
        ),
        ProviderToolDefinition(
            provider_id="fireflies",
            name="fireflies_search_transcripts",
            description="Search Fireflies transcripts using a free-text query.",
            args_schema=SearchInput,
        ),
    ),
    "github": (
        ProviderToolDefinition(
            provider_id="github",
            name="github_create_issue",
            description="Create a GitHub issue in a connected repository.",
            args_schema=IssueCreateInput,
        ),
        ProviderToolDefinition(
            provider_id="github",
            name="github_search_issues",
            description="Search GitHub issues and pull requests with a query.",
            args_schema=IssueSearchInput,
        ),
    ),
    "notion": (
        ProviderToolDefinition(
            provider_id="notion",
            name="notion_get_page",
            description="Fetch a Notion page by page ID.",
            args_schema=PageLookupInput,
        ),
        ProviderToolDefinition(
            provider_id="notion",
            name="notion_search",
            description="Search connected Notion content with a free-text query.",
            args_schema=SearchInput,
        ),
    ),
    "posthog": (
        ProviderToolDefinition(
            provider_id="posthog",
            name="posthog_get_feature_flag",
            description="Fetch a PostHog feature flag definition by key.",
            args_schema=FeatureFlagLookupInput,
        ),
        ProviderToolDefinition(
            provider_id="posthog",
            name="posthog_query_insights",
            description="Query PostHog insights with a free-text analytics prompt.",
            args_schema=InsightQueryInput,
        ),
    ),
    "vercel": (
        ProviderToolDefinition(
            provider_id="vercel",
            name="vercel_get_deployment",
            description="Fetch deployment details for a Vercel deployment ID.",
            args_schema=DeploymentLookupInput,
        ),
        ProviderToolDefinition(
            provider_id="vercel",
            name="vercel_list_projects",
            description="List Vercel projects for the connected account or team.",
            args_schema=ProjectListInput,
        ),
    ),
}


class IntegrationToolsetInitializer:
    def __init__(
        self,
        *,
        store: ConnectionStore,
        cipher: CredentialCipher,
        invoker: McpToolInvoker,
    ) -> None:
        self._store = store
        self._cipher = cipher
        self._invoker = invoker

    async def initialize(self, trigger: DiscordTriggerContext) -> AgentToolset:
        server = await self._store.get_server_by_discord_id(trigger.discord_server_id)
        if server is None:
            return AgentToolset()

        connections = await self._store.list_connections(server.id)
        tools: list[BaseTool] = []
        integrations: list[ConnectedIntegration] = []

        for connection in connections:
            if connection.status != "active":
                continue

            provider = PROVIDERS.get(connection.provider)
            tool_definitions = PROVIDER_TOOL_CATALOG.get(connection.provider)
            if provider is None or tool_definitions is None:
                continue

            credentials = self._cipher.decrypt_credentials(
                connection.credentials_encrypted
            )
            provider_tools = tuple(
                self._build_tool(
                    definition=definition,
                    credentials=credentials,
                    trigger=trigger,
                    server_id=server.id,
                )
                for definition in tool_definitions
            )

            tools.extend(provider_tools)
            integrations.append(
                ConnectedIntegration(
                    provider_id=provider.id,
                    provider_name=provider.name,
                    auth_type=provider.auth_type,
                    status=connection.status,
                    scopes=tuple(connection.scopes or ()),
                    tool_names=tuple(
                        definition.name for definition in tool_definitions
                    ),
                )
            )

        return AgentToolset(tools=tuple(tools), integrations=tuple(integrations))

    def _build_tool(
        self,
        *,
        definition: ProviderToolDefinition,
        credentials: dict[str, str],
        trigger: DiscordTriggerContext,
        server_id: str,
    ) -> BaseTool:
        async def _invoke_tool(**kwargs: object) -> object:
            result = await self._invoker.invoke(
                IntegrationToolCall(
                    provider_id=definition.provider_id,
                    tool_name=definition.name,
                    arguments=dict(kwargs),
                    credentials=credentials,
                    trigger=trigger,
                )
            )
            await self._store.touch_connection_last_used(
                server_id, definition.provider_id
            )
            return result

        return StructuredTool.from_function(
            coroutine=_invoke_tool,
            name=definition.name,
            description=definition.description,
            args_schema=definition.args_schema,
        )


def build_toolset_initializer(
    settings: AppSettings,
    *,
    invoker: McpToolInvoker | None = None,
) -> ToolsetInitializer:
    if settings.credentials_encryption_key is None:
        return EmptyToolsetInitializer()

    return IntegrationToolsetInitializer(
        store=build_connection_store(settings),
        cipher=CredentialCipher(settings.credentials_encryption_key),
        invoker=invoker or MissingMcpToolInvoker(),
    )
