# pixie-for-pm

pixie-for-pm is a Python scaffold for a Discord-triggered, LangGraph-orchestrated product collaboration system. The current scaffold sets up the core project structure, placeholder product-team agents, Discord transport wiring, and persistent LangGraph execution backed by SQLite.

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
  integrations/    # provider placeholders for Notion, GitHub, PostHog, Vercel
  orchestration/   # LangGraph workflow and runtime
  py.typed

tests/
  pixie_for_pm/    # mirrored unit coverage for routing, config, orchestration

specs/
  architecture.md  # scaffold architecture notes and extension points

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
uv run pixie-discord-bot
```

The bot entrypoint expects a populated `.env` file or equivalent environment variables. The current agent handlers are intentionally placeholder implementations and should be replaced with real prompts, tool calls, and handoff logic as the project grows.

For a full manual Discord verification flow, including Discord app setup, bot invite, channel configuration, and message-by-message e2e checks, see [tests/discord-e2e.md](/home/yiouli/repo/pixie-for-pm/tests/discord-e2e.md).

## Current Scope

This scaffold intentionally stops at a clean boundary:

- Discord transport is wired, but not yet production-hardened.
- Agent handlers return a hardcoded `E2E_PLACEHOLDER_OK` response so Discord e2e checks can confirm the loop is working.
- Integration packages exist as placeholders for future MCP-backed adapters.
- The persistent LangGraph runtime is local SQLite for development scaffolding.
  See `specs/architecture.md` for the implementation outline and extension points.
