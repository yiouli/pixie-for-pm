# Architecture Scaffold

## Goal

The scaffold establishes two coordinated surfaces for a product collaboration system with five internal agent roles:

- product manager
- market analyst
- user researcher
- data scientist
- product designer

The first surface is a single public Discord bot. The second surface is a settings system that lets each Discord server owner connect external systems for the internal agents. The settings SPA is built by Vite into `web/dist` and then served by the FastAPI process.

## Primary Flow

1. A user explicitly addresses the bot in a guild message by mentioning the bot account or replying to a prior bot message.
2. The Discord adapter normalizes the incoming message into a typed `IncomingDiscordMessage`.
3. Routing converts the message into a `DispatchRequest` that enters the product manager entrypoint.
4. The orchestrator derives a typed Discord trigger context, resolves the guild's active integrations, and expands them into a request-scoped tool bundle built from `langchain_core` tools.
5. The LangGraph runtime loads or creates thread state using the configured SQLite checkpoint store.
6. The selected placeholder agent executes with access to the typed trigger context and initialized tool bundle.
7. If the execution returns handoffs, the graph routes to the next internal agent without emitting a public Discord handoff message.
8. The current turn’s messages are returned to the Discord transport for publication as a single public bot reply.

## Discord Install Flow

1. A user opens `/` on the FastAPI web app.
2. The install page sends the browser to `GET /api/discord/install`.
3. FastAPI builds Discord's callback-less bot authorization URL with `bot applications.commands` and `DISCORD_INSTALL_PERMISSIONS`.
4. The user chooses a guild in Discord and authorizes the install.
5. The user returns to Discord and runs `/settings` in that same guild.

The scaffold is no longer single-guild at the install or `/settings` level. The bot runtime no longer depends on a configured Discord channel and only reacts when explicitly addressed.

## Integration Settings Flow

1. A user runs `/settings` in a guild where the bot is installed.
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
9. OAuth and API-key provider credentials are stored as per-server connection records in the connection store (Supabase in production, local SQLite in local runs).
10. The Discord bot's agent runtime resolves decrypted credentials **directly in Python**
    from the shared store, expands each active provider into a request-scoped tool bundle, and passes those tool objects into agent execution without serializing them into LangGraph checkpoints.

## State Model

The orchestration state keeps both a cumulative transcript and a turn-local transcript:

- `transcript` persists all agent-visible messages for checkpoint recovery.
- `turn_transcript` is reset at the start of each dispatch and contains only the current turn’s emitted messages.
- `pending_handoffs` stores structured handoff requests between agent nodes without forcing those internal transitions into the public Discord transcript.

This split allows persistent execution without forcing the Discord transport to re-send historical messages on every invocation.

## Discord Surface

The Discord client uses a single bot token for both inbound events and outbound publication.

Inbound dispatch:

- direct bot mentions
- replies to a message previously authored by the bot
- slash commands such as `/settings`

Outbound publication:

- message-triggered work returns one public bot reply for the turn
- slash-command flows defer the interaction and publish status via `edit_original_response`

## Extension Points

- Replace placeholder handlers in `pixie_for_pm/agents/registry.py` with real agent implementations.
- Extend the hosted-MCP and API-backed provider runtime layer under `pixie_for_pm/integrations/` while keeping the typed toolset initializer stable.
- Extend the FastAPI settings layer with live Supabase-backed persistence, token refresh, and provider-specific validation hardening.
- Enrich the Discord adapter with thread ownership and richer error translation.
- Swap SQLite persistence for another LangGraph-supported checkpoint backend when deployment requirements change.
