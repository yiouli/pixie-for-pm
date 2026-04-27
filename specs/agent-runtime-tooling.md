# Agent Runtime Tool Initialization Spec

## Goal

When a Discord message trigger reaches the runtime, Pixie must resolve every integration already connected for that Discord server, materialize the corresponding MCP-backed tools in a strongly typed bundle, and pass that bundle into the agent runtime for the current turn.

The runtime contract must satisfy three constraints:

1. The Discord trigger carries enough identity to resolve server-scoped credentials.
2. The initialized tool bundle is strongly typed and exposes `langchain_core` tool objects directly.
3. Tool objects stay request-scoped and are not serialized into LangGraph checkpoint state.

## Trigger Contract

Discord-triggered work must preserve the following fields from the inbound message:

- `discord_server_id`: guild ID used to resolve configured integrations
- `discord_user_id`: author ID used for auditability and future per-user routing
- `channel_id`: source channel ID
- `thread_id`: active thread ID when present
- `message_id`: trigger message ID
- `dispatch_reason`: normalized reason such as `direct_bot_mention` or `reply_to_bot`
- `thread_key`: LangGraph thread key for the turn

This data becomes a typed `DiscordTriggerContext` object that is attached to `WorkflowContext`.

## Tool Initialization Flow

### 1. Resolve request context

The Discord adapter normalizes the message into a `DispatchRequest` that includes guild and author identity.

### 2. Initialize the request-scoped toolset

Before the first agent node runs, the orchestrator asks an `IntegrationToolsetInitializer` to:

1. load the claimed server row from the shared connection store
2. list all active connections for that server
3. decrypt credentials for each connected provider
4. load live hosted MCP tools for providers that expose remote MCP servers
5. fall back to direct API-backed tools for providers without hosted MCP
6. bind the resulting tool objects to the provider credentials and trigger context

If the server has no connected integrations, the initializer returns an empty typed tool bundle.

### 2a. Emit runtime progress for the Discord surface

The message-triggered Discord surface should not stay silent while the runtime works. The orchestrator therefore accepts an optional status emitter that can be called at request-scoped milestones:

- before connected tools are resolved
- when an agent node starts running
- when a handoff changes the current internal agent
- immediately before and after a wrapped provider tool invocation

Discord can map these emitted states onto editable placeholder replies plus channel typing indicators, without leaking internal checkpoint state into the graph.

### 3. Bind the toolset into the current turn

The orchestrator builds the workflow graph for the dispatch using the request-scoped `DiscordTriggerContext` and `AgentToolset`. The graph state remains serializable because only plain workflow state is checkpointed; `BaseTool` instances live in the in-memory workflow context for that dispatch.

## Strongly Typed Runtime Format

The tool bundle is represented as an `AgentToolset` dataclass:

```python
@dataclass(frozen=True)
class AgentToolset:
    tools: tuple[BaseTool, ...]
    integrations: tuple[ConnectedIntegration, ...]

    def as_langgraph_tools(self) -> tuple[BaseTool, ...]:
        return self.tools
```

`ConnectedIntegration` carries deterministic metadata for the active provider:

- provider ID and display name
- auth type
- connection status
- granted scopes
- tool names exposed to the agent

This shape is directly consumable by LangGraph agents through `toolset.as_langgraph_tools()`.

## Provider Runtime Sources

The runtime supports two provider categories:

- Hosted MCP providers: Notion, GitHub, Vercel, and PostHog. Pixie opens remote streamable HTTP connections against the provider-hosted MCP endpoints and converts the live tool schemas into LangChain tools at dispatch time.
- Direct API providers: Airtable and Fireflies. Pixie materializes typed `StructuredTool` wrappers around the provider APIs when no hosted MCP endpoint is available.

This keeps the runtime strongly typed while avoiding any local MCP server process management or extra environment configuration.

## Operational Rules

- Only `active` connections are materialized into tools.
- Unknown providers are skipped rather than crashing the Discord turn.
- Tool names are deterministic and stable across runs.
- A successful tool invocation updates `last_used_at` for the underlying connection.
- Runtime progress updates should be best-effort UX signals; losing a status update must not fail the underlying Discord turn.
- Placeholder agent handlers can ignore the tool bundle, but real LangGraph agents can pass `toolset.as_langgraph_tools()` directly into their constructor.

## Discord UX Contract

For message-triggered turns, the Discord adapter should:

1. react to the triggering message with `:eyes:` before starting the agent loop
2. create a single placeholder reply in the eventual response location
3. edit that same reply as the orchestrator emits status updates such as `Thinking`, provider fetches, coordinator acknowledgements, and internal handoffs while relying on Discord's native typing indicator instead of a literal `Typing...` message state
4. replace the placeholder content with the final public transcript once the turn completes

## Coordinator Contract

- The coordinator is the only agent allowed to decide the next handoff destination.
- Non-coordinator agents return artifacts or blockers through private handoff context instead of producing public Discord messages.
- The runtime may therefore emit extra status updates when work returns to the coordinator for another routing decision inside the same turn.

## Code Changes

The implementation should introduce:

- a typed integration runtime module for trigger context, tool bundles, hosted MCP loading, and API-backed fallback providers
- request-scoped orchestrator initialization before graph execution
- `WorkflowContext` fields for trigger metadata and tool bundle access
- Discord normalization updates so guild ID reaches the runtime
- tests that verify both tool bundle initialization and request-scoped handler access
