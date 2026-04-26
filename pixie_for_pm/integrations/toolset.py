from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, Protocol

from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel

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


class IntegrationRuntimeProvider(Protocol):
    async def load_tools(
        self,
        *,
        credentials: Mapping[str, str],
        trigger: DiscordTriggerContext,
    ) -> tuple[BaseTool, ...]: ...


class ToolsetInitializer(Protocol):
    async def initialize(self, trigger: DiscordTriggerContext) -> AgentToolset: ...


class EmptyToolsetInitializer:
    async def initialize(self, trigger: DiscordTriggerContext) -> AgentToolset:
        del trigger
        return AgentToolset()


class IntegrationToolsetInitializer:
    def __init__(
        self,
        *,
        store: ConnectionStore,
        cipher: CredentialCipher,
        providers: Mapping[str, IntegrationRuntimeProvider],
    ) -> None:
        self._store = store
        self._cipher = cipher
        self._providers = dict(providers)

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
            runtime_provider = self._providers.get(connection.provider)
            if provider is None or runtime_provider is None:
                continue

            credentials = self._cipher.decrypt_credentials(
                connection.credentials_encrypted
            )
            try:
                provider_tools = await runtime_provider.load_tools(
                    credentials=credentials,
                    trigger=trigger,
                )
            except Exception:
                continue

            wrapped_tools = tuple(
                self._wrap_tool(
                    tool=tool,
                    provider_id=connection.provider,
                    server_id=server.id,
                )
                for tool in provider_tools
            )

            tools.extend(wrapped_tools)
            integrations.append(
                ConnectedIntegration(
                    provider_id=provider.id,
                    provider_name=provider.name,
                    auth_type=provider.auth_type,
                    status=connection.status,
                    scopes=tuple(connection.scopes or ()),
                    tool_names=tuple(tool.name for tool in wrapped_tools),
                )
            )

        return AgentToolset(tools=tuple(tools), integrations=tuple(integrations))

    def _wrap_tool(
        self,
        *,
        tool: BaseTool,
        provider_id: str,
        server_id: str,
    ) -> BaseTool:
        async def _invoke_tool(**kwargs: object) -> object:
            result = await tool.ainvoke(kwargs)
            await self._store.touch_connection_last_used(server_id, provider_id)
            return result

        response_format: Literal["content", "content_and_artifact"] = getattr(
            tool, "response_format", "content"
        )
        if response_format not in {"content", "content_and_artifact"}:
            response_format = "content"

        return StructuredTool(
            name=tool.name,
            description=tool.description,
            args_schema=_tool_args_schema(tool),
            response_format=response_format,
            metadata=tool.metadata,
            tags=tool.tags,
            return_direct=tool.return_direct,
            coroutine=_invoke_tool,
        )


def _tool_args_schema(tool: BaseTool) -> type[BaseModel] | dict[str, object]:
    if tool.args_schema is None:
        return {"type": "object", "properties": {}}
    return tool.args_schema


def build_toolset_initializer(
    settings: AppSettings,
    *,
    providers: Mapping[str, IntegrationRuntimeProvider] | None = None,
) -> ToolsetInitializer:
    if settings.credentials_encryption_key is None:
        return EmptyToolsetInitializer()

    if providers is None:
        from pixie_for_pm.integrations.runtime_providers import (
            build_runtime_providers,
        )

        providers = build_runtime_providers()

    return IntegrationToolsetInitializer(
        store=build_connection_store(settings),
        cipher=CredentialCipher(settings.credentials_encryption_key),
        providers=providers,
    )
