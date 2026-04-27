# Entry Point & Execution Flow

## How to run

The application starts with `uv run pixie`, which resolves to the `pixie_for_pm.main:main` script entry point. That starts the FastAPI app and enables the Discord bot runtime. For the retention-demo eval, the meaningful execution surface is the same one used by the bot after message normalization: an incoming Discord message is turned into a typed dispatch request, then sent through the `PixieOrchestrator`, which initializes the per-request toolset, runs the LangGraph workflow, persists checkpoints, and returns the turn transcript.

## Entry point

- **File**: `pixie_for_pm/main.py`
- **Type**: Combined ASGI server entry point with Discord bot runtime enabled
- **Framework**: FastAPI + discord.py + LangGraph orchestration

## User-facing endpoints / interface

- **Endpoint / command**: `uv run pixie`
- **Input format**: process-level startup with environment variables and optional `.env` file in the repo root
- **Output format**: running web server plus active Discord bot

- **Endpoint / command**: direct bot mention or reply to a prior bot message in Discord
- **Input format**: Discord message content plus metadata including server ID, channel ID, thread ID, author ID, and trigger type (direct mention or reply)
- **Output format**: a single user-visible reply in the same Discord thread, with internal multi-agent handoffs remaining private

- **Endpoint / command**: internal eval target for this scenario: `build_dispatch_request(IncomingDiscordMessage(...))` followed by `PixieOrchestrator.dispatch(...)`
- **Input format**: typed `IncomingDiscordMessage` carrying the same message text and Discord metadata a real message would provide
- **Output format**: `OrchestrationResult` containing the thread key and the visible turn transcript accumulated during the run

## Environment requirements

| Variable                                              | Purpose                                              | Required?                                                                         | Default                                |
| ----------------------------------------------------- | ---------------------------------------------------- | --------------------------------------------------------------------------------- | -------------------------------------- |
| `DISCORD_BOT_TOKEN`                                   | Auth token required to start the Discord bot runtime | Yes                                                                               | None                                   |
| `OPENAI_API_KEY`                                      | LLM access for PM and researcher deep-agent flows    | Required for real deep-agent behavior in this eval path                           | None                                   |
| `PRODUCT_MANAGER_MODEL`                               | Model used by the PM deep agent                      | No                                                                                | `openai:gpt-5.4`                       |
| `LANGGRAPH_CHECKPOINT_PATH`                           | SQLite checkpoint path for LangGraph persistence     | No                                                                                | `.state/pixie-langgraph.sqlite`        |
| `CONNECTION_STORE_SQLITE_PATH`                        | SQLite path for stored integration credentials       | No                                                                                | `.state/pixie-connection-store.sqlite` |
| `WEB_APP_URL`                                         | Base URL used by the settings/install surfaces       | No                                                                                | None                                   |
| `DISCORD_APPLICATION_ID` or `DISCORD_OAUTH_CLIENT_ID` | Discord app identity for install/login flows         | Needed for full Discord/settings web flows, not for the focused orchestrator eval | None                                   |
| `DISCORD_OAUTH_CLIENT_SECRET`                         | Secret for Discord OAuth in the settings web app     | Needed for login/settings flows only                                              | None                                   |
| `DISCORD_OAUTH_CALLBACK_URL`                          | Callback URL for Discord OAuth login                 | Needed for login/settings flows only                                              | None                                   |
| `SESSION_SECRET_KEY`                                  | Session cookie signing key for the web app           | Needed for settings web sessions                                                  | None                                   |
| `SUPABASE_URL`                                        | Optional Supabase backend for connection storage     | No                                                                                | None                                   |
| `SUPABASE_SERVICE_ROLE_KEY`                           | Optional Supabase service key                        | No                                                                                | None                                   |
| `CREDENTIALS_ENCRYPTION_KEY`                          | Encryption key for provider credentials              | Needed when storing credentials                                                   | None                                   |
| `OAUTH_CALLBACK_URL`                                  | Shared callback URL for external provider OAuth      | Needed for provider OAuth flows                                                   | None                                   |
