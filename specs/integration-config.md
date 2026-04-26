# Integration Configuration System — Coding Spec

## Overview

Add a web UI where users configure which external systems the PM agents can access. The Discord bot gets a `/settings` slash command that links to the web UI. The project currently has no auth system — this spec adds one.

**Supported providers:** Notion, GitHub, PostHog, Fireflies, Vercel, Airtable

---

## Relationship to Existing Code

The repo already has:

- `pixie_for_pm/integrations/` — provider placeholders for Notion, GitHub, PostHog, Vercel
- `pixie_for_pm/discord/` — bot transport, routing, and single-bot message normalization
- `pixie_for_pm/config/` — environment loading
- `pixie_for_pm/domain/` — typed workflow models
- `specs/` — architecture docs
- `changelogs/` — change history
- `tests/pixie_for_pm/` — mirrored unit tests
- `uv` for package management, `.env` pattern for config

This spec **adds** to the existing structure rather than replacing it. The integration placeholders in `pixie_for_pm/integrations/` become real once they can retrieve stored credentials through the new credential system.

---

## Architecture

```text
Discord Bot (existing)
  ├── /settings ──► replies with link: {WEB_APP_URL}/settings?server_id={guild_id}
  │                  (no API call needed — just a URL)
  │
  ├── agent needs creds ──► GET /api/internal/credentials/{server_id}/{provider}
  │                          ──► FastAPI ──► Supabase
  │
  │  (bot never talks to Supabase directly)

Vite build output (`web/dist`) ──► FastAPI serves SPA + API ──► Supabase
  user logs in with Discord, manages connections for a server_id
```

**Key model decision:** Connections are scoped per Discord server (guild), not per Discord user. A server is owned by the app user who first claims it. The bot only needs the guild ID, which it always has from the interaction context.

**New stack additions:**

- `pixie_for_pm/web/` — FastAPI app for auth + connection management + internal API for bot
- `web/` (repo root) — React + Vite frontend
- Supabase — Postgres-backed connection store (optional; not used for browser auth)
- `cryptography` — Fernet symmetric encryption for stored credentials

**Boundary rule:** The Discord bot never imports or calls Supabase. All bot interactions with the database go through FastAPI's internal endpoints (protected by `INTERNAL_API_KEY`).

---

## 1. Database Schema (Supabase)

### `users`

Managed by Supabase Auth. The `auth.users` table provides `id` (UUID) and `email`. The `user_metadata` field contains the Discord profile including `provider_id` (Discord user ID) and `full_name`.

### `servers`

Maps a Discord server (guild) to the app user who owns it.

```sql
create table public.servers (
  id uuid primary key default gen_random_uuid(),
  discord_server_id text not null unique,
  owner_user_id uuid not null references auth.users(id) on delete cascade,
  name text,                         -- optional display name
  created_at timestamptz not null default now()
);

create unique index idx_servers_discord on public.servers(discord_server_id);
create index idx_servers_owner on public.servers(owner_user_id);
```

### `connections`

Stores per-server credentials for each integration.

```sql
create table public.connections (
  id uuid primary key default gen_random_uuid(),
  server_id uuid not null references public.servers(id) on delete cascade,
  provider text not null,            -- 'notion', 'github', 'posthog', etc.
  credentials_encrypted text not null, -- Fernet-encrypted JSON blob
  scopes text[],                     -- OAuth scopes granted (null for api_key providers)
  status text not null default 'active', -- 'active' | 'expired' | 'revoked'
  connected_at timestamptz not null default now(),
  last_used_at timestamptz,

  unique(server_id, provider)
);

create index idx_connections_server on public.connections(server_id);
```

### Row-Level Security

Users can only access connections for servers they own.

```sql
alter table public.servers enable row level security;
create policy "users own servers" on public.servers
  for all using (owner_user_id = auth.uid());

alter table public.connections enable row level security;
create policy "users own server connections" on public.connections
  for all using (
    server_id in (select id from public.servers where owner_user_id = auth.uid())
  );
```

Migration file goes in `migrations/001_servers_and_connections.sql` (new directory at repo root).

---

## 2. Auth System

### 2.0 Discord Bot Installation

Pixie's bot installation flow is intentionally separate from the Discord login callback. Discord's standard bot authorization flow is callback-less, so the web app exposes a simple install redirect rather than trying to reuse `/api/auth/discord/callback`.

**Install flow:**

1. Serve the root install page at `/`.
2. Send the browser to `GET /api/discord/install`.
3. Redirect to Discord with `scope=bot applications.commands`.
4. Include the configured `DISCORD_INSTALL_PERMISSIONS` integer.
5. Let the installer choose the target server in Discord's authorize UI.
6. After authorization, instruct the user to run `/settings` in Discord to enter the authenticated settings flow.

This separation is required because the login flow expects `code` and `state` for user auth, while the install flow just adds the bot/application commands to a guild.

The public Discord surface is intentionally narrow: `/settings` is used to open the authenticated web flow, while message-triggered work starts only when a user explicitly mentions the bot or replies to a prior bot message.

### 2.1 Discord OAuth via FastAPI Session Cookies

The settings web app authenticates through FastAPI's Discord OAuth routes. Since the user is already logged into Discord in their browser, the OAuth flow usually auto-completes or requires a single "Authorize" click. FastAPI exchanges the callback code and issues an HttpOnly `session` cookie; the SPA never talks to Discord or Supabase auth directly and never stores browser auth tokens in localStorage.

**Setup:**

1. Create an OAuth2 application at discord.com/developers/applications.
2. Set the callback URI to `DISCORD_OAUTH_CALLBACK_URL`.
3. Copy Client ID and Client Secret into the web server environment.
4. Request only user-login scopes such as `identify`, `email`, and optionally `guilds`.

`DISCORD_OAUTH_CALLBACK_URL` is reserved for the settings web app login flow. Bot install flows or any broader Discord application OAuth flow should not reuse `/api/auth/discord/callback`; those need a separate route/handler because they return different scopes, permissions, and callback semantics.

**What we get from the Discord OAuth profile:**

- Discord user ID
- Discord display name
- Discord email when the `email` scope is requested

The Discord ID from the auth profile can be used for server ownership validation in future versions (e.g. checking admin permissions via Discord API).

**Frontend flow:**

```text
GET /settings?server_id=...
  → SPA calls GET /api/auth/me
  → 401 redirects browser to /api/auth/discord?next=/settings?server_id=...
  → Discord OAuth screen (auto-approves if already authorized)
  → GET /api/auth/discord/callback
  → FastAPI issues HttpOnly session cookie
  → redirect back to web UI with server_id preserved
```

### 2.2 Discord-to-Web Flow

Near-seamless because the user is already authenticated in Discord. On first use they see Discord's "Authorize" prompt once; after that it auto-completes.

```text
1. User runs /settings in Discord
2. Bot replies with ephemeral link button:
  {WEB_APP_URL}/settings?server_id={interaction.guild.id}
3. User clicks → web UI /settings?server_id=123456
4. FastAPI serves the built SPA from `web/dist`
5. If no session cookie → SPA redirects to `/api/auth/discord?next=/settings?server_id=123456`
  → Discord auto-approves (user is already logged in)
  → FastAPI callback issues session cookie and redirects back to `/settings?server_id=123456`
6. Server checks: does a servers row exist for this discord_server_id?
  a. No  → create one with current user as owner → show settings
  b. Yes, owned by current user → show settings
  c. Yes, owned by someone else → show "not authorized" message
```

### Local Development Workflow

The default local workflow uses a watch build instead of a separate Vite dev server:

```bash
cd web
npm install
npm run watch
```

In a second terminal, run:

```bash
uv run pixie-web-server
```

FastAPI serves the generated files from `web/dist` on the same origin as the API. Refresh the browser after each rebuild. Leave `VITE_API_URL` empty when using this same-origin setup.

The SettingsPage triggers the OAuth flow directly if no session exists, making the transition from Discord feel like a single click.

### 2.3 FastAPI Auth

Two auth schemes, depending on the caller:

**Frontend routes** (`/api/connections/*`, `/api/auth/*`, `/api/servers/*`) — Supabase JWT in `Authorization: Bearer <token>` header:

```python
# pixie_for_pm/web/auth.py

async def get_current_user(authorization: str = Header()) -> dict:
    token = authorization.removeprefix("Bearer ")
    result = supabase_admin.auth.get_user(token)
    if not result.user:
        raise HTTPException(401)
    return result.user
```

**Internal routes** (`/api/internal/*`) — `INTERNAL_API_KEY` in `Authorization: Bearer <key>` header:

```python
async def verify_internal_key(authorization: str = Header()) -> None:
    key = authorization.removeprefix("Bearer ")
    if key != settings.INTERNAL_API_KEY:
        raise HTTPException(401)
```

**No auth:** `GET /api/connections/oauth/callback` (uses signed state param).

### 2.4 Server Ownership Authorization

Every frontend route that touches connections requires the requesting user to own the server. This is a shared dependency:

```python
async def get_owned_server(
    server_id: str,                          # from path or query param
    user: dict = Depends(get_current_user),  # from JWT
) -> Server:
    server = await db.get_server_by_discord_id(server_id)
    if not server or server.owner_user_id != user.id:
        raise HTTPException(403, "Not authorized for this server")
    return server
```

---

## 3. Integration Providers

### Provider Registry

Extends the existing placeholder concept in `pixie_for_pm/integrations/`.

```python
# pixie_for_pm/integrations/registry.py (new file, or extend existing)

@dataclass(frozen=True)
class ProviderConfig:
    id: str                          # 'notion', 'github', etc.
    name: str                        # display name
    auth_type: Literal["oauth2", "api_key"]
    oauth_authorize_url: str | None = None
    oauth_token_url: str | None = None
    scopes: list[str] | None = None
    api_key_fields: list[str] | None = None
    api_key_help_url: str | None = None

PROVIDERS: dict[str, ProviderConfig] = { ... }
```

### Provider Details

| Provider      | Auth Type | Fields / Scopes                          | Notes                                  |
| ------------- | --------- | ---------------------------------------- | -------------------------------------- |
| **Notion**    | OAuth2    | Read content, read users                 | notion.so/my-integrations              |
| **GitHub**    | OAuth2    | `repo`, `read:org`                       | GitHub OAuth App                       |
| **Vercel**    | OAuth2    | Read deployments, read projects          | vercel.com/integrations                |
| **Airtable**  | OAuth2    | `data.records:read`, `schema.bases:read` | airtable.com/create/oauth              |
| **PostHog**   | API Key   | `api_key`, `project_id`, `host`          | Personal API key from project settings |
| **Fireflies** | API Key   | `api_key`                                | fireflies.ai/account                   |

### 3.1 OAuth2 Flow (Notion, GitHub, Vercel, Airtable)

```text
1. User clicks "Connect" on an OAuth2 provider in the web UI
2. Frontend redirects to: GET /api/connections/{provider}/authorize?server_id=...
3. Server validates user owns this server
4. Server generates HMAC-signed state param (encodes server_id + user_id + random nonce)
5. Server 302-redirects to provider's authorize URL with client_id, redirect_uri, state, scopes
6. User authorizes in provider
7. Provider redirects to: GET /api/connections/oauth/callback?code=...&state=...
8. Server validates state signature, exchanges code for tokens
9. Server encrypts tokens with Fernet, upserts into connections table
10. Server redirects to: {WEB_APP_URL}/settings?server_id=...&connected={provider}
```

### 3.2 API Key Flow (PostHog, Fireflies)

```text
1. User clicks "Connect" on an API key provider
2. Frontend expands inline form with labeled fields + link to provider docs
3. User pastes credentials, clicks Save
4. Frontend calls POST /api/connections/{provider}?server_id=... with credentials in body
5. Server validates user owns the server
6. Server makes a test API call to validate credentials
7. Valid → encrypt with Fernet, upsert into connections table, return 200
8. Invalid → return 422 with error detail
```

### 3.3 Credential Encryption

```python
# pixie_for_pm/web/encryption.py

from cryptography.fernet import Fernet

fernet = Fernet(settings.CREDENTIALS_ENCRYPTION_KEY)

def encrypt_credentials(creds: dict) -> str:
    return fernet.encrypt(json.dumps(creds).encode()).decode()

def decrypt_credentials(encrypted: str) -> dict:
    return json.loads(fernet.decrypt(encrypted.encode()).decode())
```

**Stored blob shapes:**

OAuth2 providers:

```json
{
  "access_token": "...",
  "refresh_token": "...",
  "token_type": "bearer",
  "expires_at": "..."
}
```

API key providers:

```json
{ "api_key": "...", "project_id": "...", "host": "..." }
```

---

## 4. API Endpoints

### Auth

| Method | Path           | Auth | Description              |
| ------ | -------------- | ---- | ------------------------ |
| `GET`  | `/api/auth/me` | JWT  | Return current user info |

### Servers

| Method | Path                                     | Auth | Description                                                                               |
| ------ | ---------------------------------------- | ---- | ----------------------------------------------------------------------------------------- |
| `GET`  | `/api/servers/{discord_server_id}`       | JWT  | Get server info, or 404 if unclaimed                                                      |
| `POST` | `/api/servers/{discord_server_id}/claim` | JWT  | Claim server for current user (idempotent if already owner, 409 if owned by someone else) |
| `GET`  | `/api/servers`                           | JWT  | List all servers owned by current user                                                    |

### Connections (frontend-facing)

All connection routes require `server_id` query param. Server validates user owns it.

| Method   | Path                                                  | Auth   | Description                                                    |
| -------- | ----------------------------------------------------- | ------ | -------------------------------------------------------------- |
| `GET`    | `/api/connections?server_id=...`                      | JWT    | List connections for a server (provider, status, connected_at) |
| `GET`    | `/api/connections/{provider}/authorize?server_id=...` | JWT    | Start OAuth2 flow → 302 redirect                               |
| `GET`    | `/api/connections/oauth/callback`                     | None\* | OAuth2 callback (state param carries server + user context)    |
| `POST`   | `/api/connections/{provider}?server_id=...`           | JWT    | Save API key credentials                                       |
| `DELETE` | `/api/connections/{provider}?server_id=...`           | JWT    | Disconnect — delete stored credentials                         |
| `POST`   | `/api/connections/{provider}/test?server_id=...`      | JWT    | Test if stored credentials still work                          |

### Internal (bot → server)

| Method | Path                                                       | Auth               | Description                                 |
| ------ | ---------------------------------------------------------- | ------------------ | ------------------------------------------- |
| `GET`  | `/api/internal/credentials/{discord_server_id}/{provider}` | `INTERNAL_API_KEY` | Decrypt and return credentials for a server |

Called by the Discord bot / agent process when it needs credentials to initialize an MCP client. Keyed on `discord_server_id` (the guild ID the bot always has in context). Protected by `INTERNAL_API_KEY`, not user JWTs. The bot has no Supabase dependency.

---

## 5. Frontend

### Tech

- React 19 + Vite + TypeScript
- `@supabase/supabase-js` for auth
- Tailwind CSS
- React Router

### Routes

| Route       | Component      | Description                                                                                |
| ----------- | -------------- | ------------------------------------------------------------------------------------------ |
| `/settings` | `SettingsPage` | Integration management, requires `?server_id=`. Auto-triggers Discord OAuth if no session. |

No dedicated login page is needed. The SettingsPage handles auth inline: it first calls `GET /api/auth/me`, and if that returns `401`, it redirects the browser to `/api/auth/discord?next=...` with the current settings URL preserved. From the user's perspective, clicking the Discord link and landing on settings still feels like one step.

### SettingsPage Logic

```text
1. Read server_id from query param (if missing → show error)
2. Call GET /api/auth/me
  a. 401 → redirect to /api/auth/discord?next=/settings?server_id=...
  b. 200 → continue with the authenticated profile
3. Call GET /api/servers/{server_id}
   a. 404 → call POST /api/servers/{server_id}/claim → proceed
   b. 200 + owned by current user → proceed
   c. 200 + owned by someone else → show "not authorized"
4. Call GET /api/connections?server_id=... → render provider list
```

### SettingsPage Layout

```text
┌───────────────────────────────────────────────┐
│  Pixie PM — Settings                 [Logout] │
│  Server: My Product Team                      │
├───────────────────────────────────────────────┤
│                                               │
│  Integrations                                 │
│                                               │
│  ┌───────────────────────────────────────┐    │
│  │ 🟢 Notion       Connected 3d ago     │    │
│  │                         [Disconnect]  │    │
│  ├───────────────────────────────────────┤    │
│  │ 🟢 GitHub       Connected 1w ago     │    │
│  │                         [Disconnect]  │    │
│  ├───────────────────────────────────────┤    │
│  │ ⚪ PostHog      Not connected        │    │
│  │                           [Connect]   │    │
│  ├───────────────────────────────────────┤    │
│  │ ⚪ Fireflies    Not connected        │    │
│  │                           [Connect]   │    │
│  ├───────────────────────────────────────┤    │
│  │ ⚪ Vercel       Not connected        │    │
│  │                           [Connect]   │    │
│  ├───────────────────────────────────────┤    │
│  │ ⚪ Airtable     Not connected        │    │
│  │                           [Connect]   │    │
│  └───────────────────────────────────────┘    │
│                                               │
└───────────────────────────────────────────────┘
```

- **OAuth2 providers:** "Connect" redirects browser to `/api/connections/{provider}/authorize?server_id=...`.
- **API key providers:** "Connect" expands an inline form with fields, help link, and Save button.

---

## 6. Discord Bot Changes

### New Slash Command: `/settings`

Add to `pixie_for_pm/discord/`. No API call needed — just constructs a URL with the guild ID.

```python
@bot.tree.command(name="settings", description="Configure integrations for the PM agents")
async def settings_command(interaction: discord.Interaction):
    if not interaction.guild:
        await interaction.response.send_message(
            "This command can only be used in a server.",
            ephemeral=True,
        )
        return

    url = f"{settings.WEB_APP_URL}/settings?server_id={interaction.guild.id}"
    view = discord.ui.View()
    view.add_item(discord.ui.Button(
        label="Open Settings",
        url=url,
        style=discord.ButtonStyle.link,
    ))
    await interaction.response.send_message(
        "Configure your integrations:",
        view=view,
        ephemeral=True,
    )
```

### Credential Access from Integration Placeholders

The existing placeholders in `pixie_for_pm/integrations/` gain a shared credential accessor:

```python
# pixie_for_pm/integrations/credentials.py (new)

import httpx
from pixie_for_pm.config import settings

async def get_credentials(discord_server_id: str, provider: str) -> dict | None:
    """Retrieve decrypted credentials for a server+provider from the web server."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{settings.API_URL}/api/internal/credentials/{discord_server_id}/{provider}",
            headers={"Authorization": f"Bearer {settings.INTERNAL_API_KEY}"},
        )
    if resp.status_code == 200:
        return resp.json()
    return None
```

Each integration placeholder (e.g. `pixie_for_pm/integrations/notion.py`) calls `get_credentials(guild_id, "notion")` before creating its MCP client. The guild ID is always available from the Discord message context.

---

## 7. File Structure — New and Modified Files

```text
pixie_for_pm/
  config/
    settings.py              # ← MODIFY: add new env vars
  discord/
    commands/
      settings.py            # ← NEW: /settings slash command (no API call, just URL)
  integrations/
    registry.py              # ← NEW: ProviderConfig dataclass + PROVIDERS dict
    credentials.py           # ← NEW: get_credentials() shared accessor
    notion.py                # ← MODIFY: wire credential retrieval
    github.py                # ← MODIFY: wire credential retrieval
    posthog.py               # ← MODIFY: wire credential retrieval
    vercel.py                # ← MODIFY: wire credential retrieval
    fireflies.py             # ← NEW: provider placeholder
    airtable.py              # ← NEW: provider placeholder
  web/                       # ← NEW: entire directory
    __init__.py
    app.py                   # FastAPI app, CORS, lifespan
    auth.py                  # JWT + internal API key auth dependencies
    encryption.py            # Fernet helpers
    routes/
      __init__.py
      auth_routes.py         # /api/auth/me
      server_routes.py       # /api/servers/*
      connection_routes.py   # /api/connections/*
      internal_routes.py     # /api/internal/credentials/*
    providers/
      __init__.py
      oauth.py               # OAuth2 authorize + callback logic
      api_key.py             # API key validate + store logic

web/                         # ← NEW: frontend at repo root
  src/
    main.tsx
    App.tsx                  # Router setup, Supabase auth listener
    lib/
      supabase.ts            # Supabase client init
      api.ts                 # fetch wrapper (attaches auth header)
    pages/
      SettingsPage.tsx
    components/
      ProviderCard.tsx       # Single provider row
      ApiKeyForm.tsx         # Inline form for API key providers
  index.html
  vite.config.ts
  tailwind.config.ts
  package.json
  tsconfig.json

migrations/                  # ← NEW: Supabase SQL migrations
  001_servers_and_connections.sql

tests/
  pixie_for_pm/
    web/                     # ← NEW: tests for web layer
      test_auth.py
      test_servers.py
      test_connections.py
    integrations/
      test_credentials.py   # ← NEW
      test_registry.py      # ← NEW
```

---

## 8. Environment Variables

### Additions to `.env` / `.env.example`

```bash
# --- Supabase (web server only) ---
SUPABASE_URL=
SUPABASE_ANON_KEY=
SUPABASE_SERVICE_ROLE_KEY=

# --- Credential Encryption (web server only) ---
CREDENTIALS_ENCRYPTION_KEY=        # generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# --- OAuth Providers (web server only) ---
NOTION_CLIENT_ID=
NOTION_CLIENT_SECRET=
GITHUB_CLIENT_ID=
GITHUB_CLIENT_SECRET=
VERCEL_CLIENT_ID=
VERCEL_CLIENT_SECRET=
AIRTABLE_CLIENT_ID=
AIRTABLE_CLIENT_SECRET=

# --- Web Server ---
API_URL=                           # public URL of the FastAPI server
WEB_APP_URL=                       # public URL of the React frontend
OAUTH_CALLBACK_URL=                # {API_URL}/api/connections/oauth/callback
INTERNAL_API_KEY=                   # server-to-server key, shared between bot and web server
DISCORD_APPLICATION_ID=             # optional explicit application ID for /api/discord/install
DISCORD_INSTALL_PERMISSIONS=        # optional permissions override for bot install URL
```

### Frontend `.env`

```bash
VITE_API_URL=
```

### What each process needs

| Env var                           | Web server | Discord bot | Frontend |
| --------------------------------- | :--------: | :---------: | :------: |
| `SUPABASE_*`                      |  optional  |   **no**    |    no    |
| `CREDENTIALS_ENCRYPTION_KEY`      |    yes     |     no      |    no    |
| `*_CLIENT_ID` / `*_CLIENT_SECRET` |    yes     |     no      |    no    |
| `API_URL`                         |    yes     |     yes     |   yes    |
| `WEB_APP_URL`                     |    yes     |     yes     |    no    |
| `INTERNAL_API_KEY`                |    yes     |     yes     |    no    |

The bot only needs `API_URL`, `WEB_APP_URL`, and `INTERNAL_API_KEY` as new env vars. `WEB_APP_URL` is just for constructing the settings link — no API call is made. All existing bot env vars (`DISCORD_TOKEN`, `LANGGRAPH_CHECKPOINT_PATH`, etc.) remain unchanged.

---

## 9. New Dependencies

### Python (add to `pyproject.toml`)

```text
fastapi
uvicorn[standard]
supabase
cryptography
httpx
```

### Frontend (`web/package.json`)

```text
react, react-dom, react-router-dom
tailwindcss, @tailwindcss/vite
typescript, vite, @vitejs/plugin-react, vitest
```

---

## 10. Entrypoints

The project currently has one entrypoint: `pixie-discord-bot`.

Add a second entrypoint in `pyproject.toml`:

```toml
[project.scripts]
pixie-discord-bot = "pixie_for_pm.discord.bot:main"
pixie-web-server = "pixie_for_pm.web.app:main"     # ← NEW
```

The web server runs independently from the Discord bot. In dev:

```bash
uv run pixie-web-server        # FastAPI on port 8000
cd web && npm run dev           # Vite on port 5173
uv run pixie-discord-bot       # Discord bot (existing)
```

---

## 11. Implementation Order

1. **Supabase project setup** — create project and run `migrations/001_servers_and_connections.sql`
2. **Config updates** — add new env vars to `pixie_for_pm/config/settings.py` and `.env.example`
3. **`pixie_for_pm/web/` skeleton** — FastAPI app, CORS, health check, `pixie-web-server` entrypoint
4. **Auth layer** — Discord session cookie dependency, `GET /api/auth/me`, `GET /api/auth/discord`
5. **Frontend skeleton** — Vite + React + Router + SettingsPage with backend-owned Discord OAuth redirect
6. **Server ownership** — `POST /api/servers/{id}/claim`, `GET /api/servers/{id}`, SettingsPage claim-on-first-visit flow
7. **Provider registry** — `pixie_for_pm/integrations/registry.py` with all 6 providers
8. **API key flow** — PostHog + Fireflies: form, validate, encrypt, store
9. **OAuth2 flow** — start with Notion (simplest), then GitHub, Vercel, Airtable
10. **Settings page** — ProviderCard, connect/disconnect, status display
11. **`/settings` slash command** — add to Discord bot (just a URL, no API call)
12. **Internal credentials endpoint** — `GET /api/internal/credentials/{server_id}/{provider}`
13. **Wire integration placeholders** — `credentials.py` accessor, update existing placeholders
14. **Tests** — server claim, connection CRUD, credential encryption round-trip
15. **Token refresh** — background job for OAuth2 token refresh (can defer to v2)

---

## 12. Security Checklist

- [ ] Credentials encrypted at rest with Fernet
- [ ] `CREDENTIALS_ENCRYPTION_KEY` stored as env var, never committed
- [ ] OAuth2 state params HMAC-signed to prevent CSRF
- [ ] Internal credentials endpoint requires `INTERNAL_API_KEY` (not user JWT)
- [ ] RLS enabled on `servers` and `connections` tables
- [ ] Server ownership checked on every connection mutation
- [ ] CORS restricted to `WEB_APP_URL` origin only
- [ ] All credential input over HTTPS (never through Discord messages)
- [ ] OAuth2 scopes minimized (read-only where possible)
- [ ] `SUPABASE_SERVICE_ROLE_KEY` used server-side only, never in frontend
- [ ] Discord guild IDs are not secret, but server claim is first-come-first-served (acceptable for v1; add transfer/unclaim in v2 if needed)
