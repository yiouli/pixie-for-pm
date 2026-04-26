# Discord E2E Guide

This guide walks through a full manual end-to-end test from Discord into the bot, through LangGraph orchestration, and back into Discord.

## What This Verifies

The e2e flow verifies all of the following in one pass:

- the Discord bot can connect to your server
- explicit mention and reply triggers work
- message normalization and routing work
- LangGraph runs the selected placeholder agent
- SQLite checkpoint persistence is created locally
- the bot sends a response back to Discord

The expected placeholder response always starts with `E2E_PLACEHOLDER_OK`.

## Prerequisites

- Python 3.11+
- `uv` installed
- access to a Discord server where you can add a bot
- permission to create a Discord application and bot

## 1. Install Dependencies

From the repository root:

```bash
uv sync
```

## 2. Create the Discord Bot

In the Discord Developer Portal:

1. Create a new application.
2. Open the `Bot` section.
3. Create a bot user.
4. Enable `Message Content Intent`.
5. Copy the bot token.

## 3. Install the Bot Through the Pixie Web App

Build the frontend once and start the web server:

```bash
cd web
npm install
npm run build
cd ..
uv run pixie-web-server
```

Then, in a browser:

1. Open `http://localhost:8000/`.
2. Click `Install Pixie to Discord`.
3. Confirm Discord opens the authorize screen for your application.
4. Choose the target server in Discord and authorize the install there.

The install route is callback-less by design. After Discord confirms the install, return to your server and use `/settings` there.

For automated browser verification of the install surface, run:

```bash
cd web
npm run test:e2e -- tests/e2e/install.spec.ts
```

## 4. Create a Test Channel in Discord

Create one channel in the target server for orchestration traffic, for example:

- `#pixie-lab`

You only need one channel for the basic e2e flow. Webhooks are optional for the first pass.

## 5. Collect Discord IDs

In Discord, enable Developer Mode and then collect:

1. the server ID

## 6. Configure `.env`

Start from the example file:

```bash
cp .env.example .env
```

Set at least these values:

```dotenv
DISCORD_BOT_TOKEN=your-bot-token
CONNECTION_STORE_SQLITE_PATH=.state/pixie-connection-store.sqlite
LANGGRAPH_CHECKPOINT_PATH=.state/pixie-langgraph.sqlite
```

For local runs without Supabase, `CONNECTION_STORE_SQLITE_PATH` is how the web app and the bot share per-server channel configuration and credentials across separate processes.
For local runs without Supabase, `CONNECTION_STORE_SQLITE_PATH` is how the web app and the bot share claimed servers and credentials across separate processes.

The default mention tokens in `.env.example` are already enough for a first e2e run:

- `@pm`
- `@market`
- `@uxr`
- `@data`
- `@design`

You do not need webhook URLs for the first test. If webhook URLs are empty, the bot falls back to normal channel messages with the persona display name prefixed.

## 7. Start the Bot

Run:

```bash
uv run pixie-discord-bot
```

Keep that terminal open while testing in Discord.

## 8. Claim the Server Through `/settings`

In any channel in the Discord server:

1. Run `/settings`.
2. Click the settings link.
3. Finish Discord login if prompted.
4. Confirm the settings page shows the same server ID.

This step claims the server for your account so settings and provider credentials can be attached to that Discord server.

## 9. Run the Basic E2E Checks in Discord

Open any channel in the installed Discord server and send the following messages.

### Check A: Direct Bot Mention Routes to Product Manager

Send:

```text
@Pixie can you help me test the bot?
```

Expected result:

- the bot replies in the same channel
- the response starts with `E2E_PLACEHOLDER_OK`
- the response mentions `product manager`

Example shape:

```text
E2E_PLACEHOLDER_OK [product manager] Discord -> LangGraph -> agent -> Discord loop is working. Original message: Can you help me test the Pixie bot?
```

### Check B: Explicit Agent Mention Routing

Send each of these one by one:

```text
@market please verify the routing
@uxr please verify the routing
@data please verify the routing
@design please verify the routing
@pm please verify the routing
```

Expected result for each message:

- the bot replies once
- the response starts with `E2E_PLACEHOLDER_OK`
- the response includes the matching agent name

### Check C: Thread Reply Routing

1. Start a thread from any previous bot response.
2. Reply inside that thread with:

```text
Can you continue in this thread?
```

Expected result:

- the bot responds inside the thread
- the response starts with `E2E_PLACEHOLDER_OK`
- the response comes from the same agent persona path that produced the message you replied to

## 10. Verify Local Persistence

After sending at least one Discord message, confirm the SQLite files exist:

```bash
ls -l .state/pixie-langgraph.sqlite
ls -l .state/pixie-connection-store.sqlite
```

Expected result:

- both files exist
- the checkpoint file timestamp updates as you continue sending messages

## 11. Optional Persona Webhook Check

If you want each agent to appear with a separate Discord name and avatar:

1. Create a webhook for the test channel.
2. Put the webhook URL into the matching `DISCORD_<ROLE>_WEBHOOK_URL` variable.
3. Restart the bot.

Expected result:

- responses still start with `E2E_PLACEHOLDER_OK`
- outbound messages render with the configured persona display name instead of the plain fallback prefix

## Fast Troubleshooting

If the bot does not respond:

- verify the install flow completed and the bot appears in the server member list
- verify the bot and web server are using the same `CONNECTION_STORE_SQLITE_PATH` when Supabase is not configured
- verify `Message Content Intent` is enabled
- verify you explicitly mentioned the bot or an agent token such as `@pm`
- verify the bot can read and send messages in the test channel
- verify you started the bot from the repository root with `uv run pixie-discord-bot`

If the bot responds in the wrong agent persona:

- verify your mention tokens match the values in `.env`
- remember that messages with no mention default to the product manager
- remember that replies route back to the replied-to agent when the display name matches a configured persona

If persistence is not created:

- verify the process can write to `.state/`
- verify `LANGGRAPH_CHECKPOINT_PATH` points to a writable location

## Recommended E2E Sequence

For a quick smoke test, use this order:

1. start the bot
2. run `/settings` once and open the settings page
3. send one bot mention and confirm the product manager response
4. send `@market please verify the routing`
5. open a thread and reply inside it
6. verify both SQLite files exist

If all six checks pass, the Discord-to-LangGraph-to-Discord loop is working.
