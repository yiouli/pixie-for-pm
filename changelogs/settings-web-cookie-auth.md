# Settings Web Cookie Auth

- removed the stale frontend Supabase auth client that redirected unauthenticated settings visits to `https://invalid.local`
- switched the settings SPA to FastAPI-owned Discord login via `/api/auth/discord?next=...`, preserving the current `server_id` URL during login
- updated the frontend API client to rely on session cookies instead of browser-side bearer tokens
- fixed the Discord login state handling by separating the CSRF token from the post-login redirect path, avoiding quoted-cookie mismatches in real browsers
- updated Python settings loading so the repo-local `.env` file overrides stale inherited shell values during local runs
- added a frontend regression test for the Discord login redirect helper and updated docs/specs to match the cookie-based auth flow
