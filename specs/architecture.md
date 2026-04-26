# Architecture Scaffold

## Goal

The scaffold establishes a Discord-first orchestration surface for a product collaboration system with five agent roles:

- product manager
- market analyst
- user researcher
- data scientist
- product designer

## Primary Flow

1. A user sends a message in the configured orchestration channel or one of its threads.
2. The Discord adapter normalizes the incoming message into a typed `IncomingDiscordMessage`.
3. Routing chooses an `AgentRole` using this precedence:
   - first explicit persona mention token
   - reply target persona
   - default product manager fallback
4. The adapter converts that into a `DispatchRequest`.
5. The LangGraph runtime loads or creates thread state using the configured SQLite checkpoint store.
6. The selected placeholder agent executes.
7. If the execution returns handoffs, the graph emits a synthetic handoff message and routes to the next agent.
8. The current turn’s messages are returned to the Discord transport for publication.

## State Model

The orchestration state keeps both a cumulative transcript and a turn-local transcript:

- `transcript` persists all agent-visible messages for checkpoint recovery.
- `turn_transcript` is reset at the start of each dispatch and contains only the current turn’s emitted messages.
- `pending_handoffs` stores structured handoff requests between agent nodes.

This split allows persistent execution without forcing the Discord transport to re-send historical messages on every invocation.

## Discord Surface

The Discord client uses a single bot token for inbound events and optional per-agent webhooks for outbound persona rendering.

Inbound dispatch:

- token-based mentions such as `@pm`
- raw Discord mention strings such as `<@&role-id>`
- replies to a message previously authored by an agent persona

Outbound publication:

- webhook send with persona display name when a webhook URL exists
- channel send fallback prefixed with the persona display name when no webhook exists

## Extension Points

- Replace placeholder handlers in `pixie_for_pm/agents/registry.py` with real agent implementations.
- Add MCP-backed adapters under `pixie_for_pm/integrations/`.
- Enrich the Discord adapter with thread ownership, slash commands, and richer error translation.
- Swap SQLite persistence for another LangGraph-supported checkpoint backend when deployment requirements change.
