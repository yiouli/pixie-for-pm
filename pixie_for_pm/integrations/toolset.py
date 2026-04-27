from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal, Protocol

import pixie
from langchain_core.messages import ToolMessage
from langchain_core.tools import BaseTool, StructuredTool
from pixie.instrumentation.wrap import get_eval_input
from pydantic import BaseModel

from pixie_for_pm.config.settings import AppSettings
from pixie_for_pm.domain.models import StatusEmitter, emit_status_update
from pixie_for_pm.integrations.registry import PROVIDERS
from pixie_for_pm.web.encryption import CredentialCipher
from pixie_for_pm.web.store import build_connection_store

if TYPE_CHECKING:
    from pixie_for_pm.web.store import ConnectionStore


logger = logging.getLogger(__name__)


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
class IntegrationLoadFailure:
    provider_id: str
    provider_name: str
    status: str
    error: str


@dataclass(frozen=True)
class AgentToolset:
    tools: tuple[BaseTool, ...] = ()
    integrations: tuple[ConnectedIntegration, ...] = ()
    failures: tuple[IntegrationLoadFailure, ...] = ()

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
    async def initialize(
        self,
        trigger: DiscordTriggerContext,
        *,
        status_emitter: StatusEmitter | None = None,
    ) -> AgentToolset: ...


class EmptyToolsetInitializer:
    async def initialize(
        self,
        trigger: DiscordTriggerContext,
        *,
        status_emitter: StatusEmitter | None = None,
    ) -> AgentToolset:
        del trigger, status_emitter
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
        self._tool_call_counts: dict[str, int] = {}

    def _next_tool_call_index(self, tool_name: str) -> int:
        index = self._tool_call_counts.get(tool_name, 0) + 1
        self._tool_call_counts[tool_name] = index
        return index

    async def initialize(
        self,
        trigger: DiscordTriggerContext,
        *,
        status_emitter: StatusEmitter | None = None,
    ) -> AgentToolset:
        server = await self._store.get_server_by_discord_id(trigger.discord_server_id)
        if server is None:
            return AgentToolset()

        connections = await self._store.list_connections(server.id)
        tools: list[BaseTool] = []
        integrations: list[ConnectedIntegration] = []
        failures: list[IntegrationLoadFailure] = []

        for connection in connections:
            if connection.status != "active":
                continue

            provider = PROVIDERS.get(connection.provider)
            runtime_provider = self._providers.get(connection.provider)
            if provider is None or runtime_provider is None:
                continue

            credentials = dict(
                self._cipher.decrypt_credentials(connection.credentials_encrypted)
            )
            original_credentials = dict(credentials)
            try:
                provider_tools = await runtime_provider.load_tools(
                    credentials=credentials,
                    trigger=trigger,
                )
            except Exception as exc:
                logger.exception(
                    "Integration tool initialization failed provider=%s "
                    "discord_server_id=%s thread_key=%s dispatch_reason=%s",
                    provider.id,
                    trigger.discord_server_id,
                    trigger.thread_key,
                    trigger.dispatch_reason,
                )
                failures.append(
                    IntegrationLoadFailure(
                        provider_id=provider.id,
                        provider_name=provider.name,
                        status=connection.status,
                        error=str(exc),
                    )
                )
                continue

            if credentials != original_credentials:
                await self._store.upsert_connection(
                    server.id,
                    connection.provider,
                    self._cipher.encrypt_credentials(credentials),
                    connection.scopes,
                    connection.status,
                )

            wrapped_tools = tuple(
                self._wrap_tool(
                    tool=tool,
                    provider_id=connection.provider,
                    provider_name=provider.name,
                    server_id=server.id,
                    trigger=trigger,
                    status_emitter=status_emitter,
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

        return AgentToolset(
            tools=tuple(tools),
            integrations=tuple(integrations),
            failures=tuple(failures),
        )

    def _wrap_tool(
        self,
        *,
        tool: BaseTool,
        provider_id: str,
        provider_name: str,
        server_id: str,
        trigger: DiscordTriggerContext,
        status_emitter: StatusEmitter | None,
    ) -> BaseTool:
        response_format: Literal["content", "content_and_artifact"] = getattr(
            tool, "response_format", "content"
        )
        if response_format not in {"content", "content_and_artifact"}:
            response_format = "content"

        async def _invoke_tool(**kwargs: object) -> object:
            await emit_status_update(
                status_emitter,
                f"Fetching data from {provider_name}...",
            )
            call_index = self._next_tool_call_index(tool.name)
            wrap_name = f"tool_call__{tool.name}__{call_index}"
            args_wrap_name = f"tool_args__{tool.name}__{call_index}"
            pixie.wrap(
                {"tool": tool.name, "args": _jsonable(kwargs)},
                purpose="state",
                name=args_wrap_name,
                description=(
                    f"Args passed to {tool.name} (call #{call_index}) so evaluators "
                    "can inspect what content was sent to the integration."
                ),
            )
            try:
                if get_eval_input() is not None:
                    # Eval mode: skip the real network call, return registry value.
                    # If the agent invents a tool call we didn't capture in the
                    # reference trace, return a synthetic tool error so the LLM
                    # can recover and the run still produces a scorable transcript.
                    sentinel: object = object()

                    def _placeholder() -> object:
                        return sentinel

                    try:
                        injected = pixie.wrap(
                            _placeholder,
                            purpose="input",
                            name=wrap_name,
                            description=(
                                f"Result of {tool.name} (call #{call_index}) replayed "
                                "from the eval registry."
                            ),
                        )()
                    except Exception as miss_exc:
                        message = (
                            f"[eval-stub] {tool.name} call #{call_index} not in "
                            f"reference trace ({type(miss_exc).__name__}). "
                            "Treat as a transient tool failure and continue."
                        )
                        if response_format == "content_and_artifact":
                            wrapped_result: object = (message, None)
                        else:
                            wrapped_result = message
                    else:
                        if injected is sentinel:
                            raise RuntimeError(
                                f"Eval registry did not provide a value for {wrap_name}."
                            )
                        if response_format == "content_and_artifact":
                            if isinstance(injected, list) and len(injected) == 2:
                                wrapped_result = (injected[0], injected[1])
                            elif isinstance(injected, tuple) and len(injected) == 2:
                                wrapped_result = injected
                            else:
                                wrapped_result = (injected, None)
                        else:
                            wrapped_result = injected
                elif response_format == "content_and_artifact":
                    result = await tool.ainvoke(
                        {
                            "type": "tool_call",
                            "id": f"wrapped-{provider_id}-{tool.name}",
                            "name": tool.name,
                            "args": kwargs,
                        }
                    )
                    if isinstance(result, ToolMessage):
                        wrapped_result = (result.content, result.artifact)
                    elif isinstance(result, tuple):
                        wrapped_result = result
                    else:
                        wrapped_result = (result, None)
                    pixie.wrap(
                        _jsonable(wrapped_result),
                        purpose="input",
                        name=wrap_name,
                        description=(
                            f"Captured result of {tool.name} (call #{call_index}) "
                            "from the live integration."
                        ),
                    )
                else:
                    wrapped_result = await tool.ainvoke(kwargs)
                    pixie.wrap(
                        _jsonable(wrapped_result),
                        purpose="input",
                        name=wrap_name,
                        description=(
                            f"Captured result of {tool.name} (call #{call_index}) "
                            "from the live integration."
                        ),
                    )
            except Exception:
                logger.exception(
                    "Tool invocation failed provider=%s tool=%s discord_server_id=%s "
                    "thread_key=%s channel_id=%s message_id=%s dispatch_reason=%s "
                    "arg_keys=%s",
                    provider_id,
                    tool.name,
                    trigger.discord_server_id,
                    trigger.thread_key,
                    trigger.channel_id,
                    trigger.message_id,
                    trigger.dispatch_reason,
                    ",".join(sorted(kwargs)) or "none",
                )
                raise
            await self._store.touch_connection_last_used(server_id, provider_id)
            await emit_status_update(
                status_emitter,
                f"Analyzing results from {provider_name}...",
            )
            return wrapped_result

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


def _jsonable(value: Any) -> Any:
    """Best-effort coercion of tool I/O into JSON-serialisable shapes for wrap()."""
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, Mapping):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, ToolMessage):
        return {
            "content": _jsonable(value.content),
            "artifact": _jsonable(value.artifact),
        }
    return str(value)


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
