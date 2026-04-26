# Architecture Scaffold

## Goal

The scaffold establishes two coordinated surfaces for a product collaboration system with five agent roles:

- product manager
- market analyst
- user researcher
- data scientist
- product designer

The first surface is the existing Discord orchestration loop. The second surface is a settings system that lets each Discord server owner connect external systems for the agents. The settings SPA is built by Vite into `web/dist` and then served by the FastAPI process.

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

## Integration Settings Flow

1. A user runs `/settings` in the configured guild.
2. The bot replies with an ephemeral link to the web app, preserving the Discord server ID.
3. FastAPI serves the built SPA bundle for that link, and the browser loads the settings UI from the same origin as the API.
4. The user opens the link and, if not already logged in, is redirected to Discord OAuth
   (`GET /api/auth/discord`).
5. Discord redirects to `GET /api/auth/discord/callback`. The server exchanges the code for
   a Discord access token, fetches the Discord user identity from `/users/@me`, and issues
   a signed Fernet-encrypted `session` HttpOnly cookie.
6. The browser is redirected back to the web app with the session cookie set.
7. The web app calls `POST /api/servers/{discord_server_id}/claim` to record ownership.
8. The FastAPI API validates ownership on every subsequent settings mutation.
9. OAuth and API-key provider credentials are stored as Fernet-encrypted per-server
   connection records in the connection store (Supabase in production, in-memory in tests).
10. The Discord bot's agent runtime accesses decrypted credentials **directly in Python**
    via `pixie_for_pm.integrations.credentials.get_credentials(discord_server_id, provider,
store=store, cipher=cipher)` — no HTTP bridge is needed.

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
- Add richer MCP-backed adapters under `pixie_for_pm/integrations/` on top of the shared credential accessor.
- Extend the FastAPI settings layer with live Supabase-backed persistence, token refresh, and provider-specific validation hardening.
- Enrich the Discord adapter with thread ownership and richer error translation.
- Swap SQLite persistence for another LangGraph-supported checkpoint backend when deployment requirements change.
