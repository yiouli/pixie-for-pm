# pixie-for-pm

pixie-for-pm is a Discord-triggered, LangGraph-orchestrated product collaboration system with a companion settings surface for managing external integrations per Discord server. The repository now includes the Discord bot, a FastAPI settings API, and a React/Vite frontend that is built into `web/dist` and served by FastAPI.

## Agents

The scaffold keeps five internal agent roles, each with a placeholder execution function:

- product manager
- market analyst
- user researcher
- data scientist
- product designer

Discord exposes a single public bot identity. Users start work by mentioning the bot, replying to a prior bot message, or using a slash command. LangGraph can still hand work across internal agents, but those handoffs are not rendered as separate Discord personas or synthetic in-channel messages.

## Architecture

The package layout follows explicit boundaries:

```text
pixie_for_pm/
  agents/          # placeholder agent handlers and registry
  config/          # environment loading
  discord/         # routing, bot mention normalization, bot transport shell
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

1. Discord receives a message that explicitly addresses the bot through a bot mention or a reply to a prior bot message.
2. The Discord adapter normalizes message content into a typed dispatch request.
3. Routing enters the product manager entrypoint while preserving whether the trigger was a direct mention or a reply.
4. LangGraph invokes the internal agents it needs and persists checkpoint state to SQLite.
5. Internal handoffs stay inside the orchestration graph instead of being emitted as Discord messages.
6. The Discord adapter publishes a single bot reply for the turn. Slash-command follow-up state is delivered through deferred interaction responses.

The Discord install flow is:

1. A user opens `/` on the FastAPI-hosted web app.
2. The install page links to `/api/discord/install`.
3. FastAPI redirects the browser to Discord's callback-less bot authorization URL with `bot applications.commands` and the minimum permissions needed for the current e2e loop.
4. The installer chooses the Discord server in Discord's own authorize UI.
5. After authorization, the user runs `/settings` inside that server to enter the authenticated settings flow.

The integration settings flow is:

1. A Discord user runs `/settings` in a guild where the bot is installed.
2. The bot replies with an ephemeral link to `/settings?server_id=<guild-id>` on the FastAPI-hosted web app.
3. FastAPI serves the built SPA from `web/dist`, and the browser loads the settings UI from the same origin as the API.
4. The settings UI establishes a Discord-backed session and claims the Discord server for the current app user.
5. The FastAPI server stores encrypted connection credentials in the shared connection store.
6. The bot and agent-side integrations read the same shared store, keyed by Discord server ID.

## Persistence

LangGraph persistence is enabled through `AsyncSqliteSaver`. The checkpoint database path is configured with `LANGGRAPH_CHECKPOINT_PATH`, which defaults in the example environment to `.state/pixie-langgraph.sqlite`.

## Discord Bot Surface

Pixie uses one installed Discord bot identity for all public communication.

- inbound triggers are direct bot mentions, replies to prior bot-authored messages, and slash commands
- internal LangGraph handoffs remain private to the orchestration layer
- slash-command status updates should use deferred interaction replies and edits instead of agent-to-agent Discord messages

## Local Setup

```bash
uv sync
cp .env.example .env
uv run pytest
uv run mypy .
uv run ruff check .
uv run pixie
```

To run the settings UI locally:

```bash
cd web
npm install
npm run build
```

For active web development, run the frontend build in watch mode in one terminal and the combined backend in another:

```bash
cd web
npm install
npm run watch
```

```bash
uv run pixie-web-server
```

Or run the full local runtime, including the Discord bot, with:

```bash
uv run pixie
```

Open `http://localhost:8000`. FastAPI serves the latest files from `web/dist`, so refreshing the page picks up each watched rebuild. `npm run dev` is no longer the default local workflow for this repo.

The root page at `http://localhost:8000/` is the install surface for the Discord bot. The installer now chooses the target server in Discord's authorize UI instead of Pixie preselecting one.

The bot no longer relies on any configured Discord channel. It reacts only when explicitly addressed: a direct bot mention or a reply to a previous bot message.

Create `web/.env` from `web/.env.example`. Leave `VITE_API_URL` empty to use the same origin as FastAPI, or set it explicitly only when the frontend should call a different API host.

The bot entrypoint expects a populated `.env` file or equivalent environment variables. The current agent handlers are intentionally placeholder implementations and should be replaced with real prompts, tool calls, and handoff logic as the project grows.

The settings API expects session and encryption keys plus OAuth client credentials. Supabase remains optional; when it is not configured, both the web app and bot default to the shared local SQLite store at `CONNECTION_STORE_SQLITE_PATH` so local end-to-end flows work across a single combined process or separate processes.

For Vercel, deploy the ASGI app exposed at `api/index.py`. That deployment surface serves FastAPI and the built SPA, but it intentionally does not start the long-lived Discord gateway client.

To validate the browser-visible install flow locally, run:

```bash
cd web
npm run test:e2e -- tests/e2e/install.spec.ts
```

For a full manual Discord verification flow, including Discord app setup, bot invite, channel configuration, and message-by-message e2e checks, see [docs/discord-e2e.md](/home/yiouli/repo/pixie-for-pm/docs/discord-e2e.md).

## Current Scope

This scaffold now covers the first integration-management slice:

- Discord transport handles direct bot mentions, replies to bot-authored messages, and the `/settings` slash command.
- FastAPI exposes the bot install page/redirect, settings, claim, connection, OAuth callback, and internal credential routes.
- Credentials are encrypted before storage and decrypted only on the internal server-to-server path.
- The web frontend provides the initial settings UX for OAuth and API-key providers.
- Agent handlers still use placeholder business logic, and live storage/provider wiring should be verified in deployment.

See `specs/architecture.md` and `specs/integration-config.md` for the implementation outline and extension points.
