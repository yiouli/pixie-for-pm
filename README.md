# pixie-for-pm

pixie-for-pm is a Discord-triggered, LangGraph-orchestrated product collaboration system with a companion settings surface for managing external integrations per Discord server. The repository now includes the Discord bot, a FastAPI settings API, and a React/Vite frontend that is built into `web/dist` and served by FastAPI.

## Agents

The scaffold includes five agent roles, each with a dedicated Discord persona surface and a placeholder execution function:

- product manager
- market analyst
- user researcher
- data scientist
- product designer

Messages without an explicit agent mention default to the product manager. Replies to an agent-authored message route back to that same agent. Agents can hand work off internally through the orchestration layer, and the scaffold emits a synthetic handoff message so Discord users see the delegation happen in-channel.

## Architecture

The package layout follows explicit boundaries:

```text
pixie_for_pm/
  agents/          # placeholder agent handlers and registry
  config/          # environment loading and persona configuration
  discord/         # routing, mention parsing, bot transport shell
  domain/          # typed workflow models shared across layers
  integrations/    # provider registry and credential access helpers
  orchestration/   # LangGraph workflow and runtime
  web/             # FastAPI settings API, auth, routes, encryption
  py.typed

tests/
  pixie_for_pm/    # mirrored unit coverage for config, Discord, web, orchestration

web/
  src/             # React + Vite settings UI source
  dist/            # built SPA served by FastAPI

specs/
  architecture.md  # architecture notes and extension points
  integration-config.md

changelogs/
  initial-scaffold.md
```

The runtime flow is:

1. Discord receives a message in the configured orchestration channel or one of its threads.
2. The Discord adapter normalizes message content into a typed dispatch request.
3. Routing selects the mentioned agent, reply target, or the default product manager.
4. LangGraph invokes the selected placeholder agent and persists checkpoint state to SQLite.
5. If an agent requests a handoff, the orchestration layer generates a synthetic handoff message and then routes control to the target agent.
6. The Discord adapter publishes the current turn’s agent messages back to the thread using persona webhooks when configured, with a bot-message fallback when they are not.

The integration settings flow is:

1. A Discord user runs `/settings` in the configured guild.
2. The bot replies with an ephemeral link to `/settings?server_id=<guild-id>` on the FastAPI-hosted web app.
3. FastAPI serves the built SPA from `web/dist`, and the browser loads the settings UI from the same origin as the API.
4. The settings UI establishes a Discord-backed Supabase session and claims the Discord server for the current app user.
5. The FastAPI server stores encrypted connection credentials per server and provider.
6. Agent-side integrations fetch decrypted credentials through the internal API, keyed by Discord server ID and protected with `INTERNAL_API_KEY`.

## Persistence

LangGraph persistence is enabled through `AsyncSqliteSaver`. The checkpoint database path is configured with `LANGGRAPH_CHECKPOINT_PATH`, which defaults in the example environment to `.state/pixie-langgraph.sqlite`.

## Discord Persona Model

Each agent persona is configured with:

- a display name
- one or more mention tokens used for inbound dispatch
- an optional webhook URL used to send messages with that persona’s avatar and name

The scaffold supports plain-text aliases such as `@pm` as well as raw Discord mention strings like `<@&role-id>` when you map a Discord role to an agent persona.

## Local Setup

```bash
uv sync
cp .env.example .env
uv run pytest
uv run mypy .
uv run ruff check .
uv run pixie-web-server
uv run pixie-discord-bot
```

To run the settings UI locally:

```bash
cd web
npm install
npm run build
```

For active web development, run the frontend build in watch mode in one terminal and the FastAPI server in another:

```bash
cd web
npm install
npm run watch
```

```bash
uv run pixie-web-server
```

Open `http://localhost:8000`. FastAPI serves the latest files from `web/dist`, so refreshing the page picks up each watched rebuild. `npm run dev` is no longer the default local workflow for this repo.

Create `web/.env` from `web/.env.example`. Leave `VITE_API_URL` empty to use the same origin as FastAPI, or set it explicitly only when the frontend should call a different API host.

The bot entrypoint expects a populated `.env` file or equivalent environment variables. The current agent handlers are intentionally placeholder implementations and should be replaced with real prompts, tool calls, and handoff logic as the project grows.

The settings API expects session and encryption keys plus OAuth client credentials. Supabase remains optional as a persisted connection store, and the current test suite exercises the API against an injected in-memory store so route behavior stays deterministic during local development.

For a full manual Discord verification flow, including Discord app setup, bot invite, channel configuration, and message-by-message e2e checks, see [docs/discord-e2e.md](/home/yiouli/repo/pixie-for-pm/docs/discord-e2e.md).

## Current Scope

This scaffold now covers the first integration-management slice:

- Discord transport handles message routing plus a guild-scoped `/settings` command.
- FastAPI exposes settings, claim, connection, OAuth callback, and internal credential routes.
- Credentials are encrypted before storage and decrypted only on the internal server-to-server path.
- The web frontend provides the initial settings UX for OAuth and API-key providers.
- Agent handlers still use placeholder business logic, and live storage/provider wiring should be verified in deployment.

See `specs/architecture.md` and `specs/integration-config.md` for the implementation outline and extension points.
