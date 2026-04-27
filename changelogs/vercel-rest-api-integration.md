# Vercel REST API Integration

The previous Vercel integration was wired through Vercel's hosted MCP server with an OAuth2/PKCE login flow. That flow only authenticates a user for sign-in to Vercel and the hosted MCP server does not expose deployment-creation tools, so the product designer agent could never actually publish a clickable prototype.

This change replaces that integration with a direct Vercel REST API integration authenticated by a personal Vercel API access token (see [Vercel's access-token guide](https://vercel.com/kb/guide/how-do-i-use-a-vercel-api-access-token)).

## Behavior changes

- Vercel is now an `api_key` provider (single field: `access_token`). The Settings page exposes a token entry form linking to the Vercel access-token docs instead of an OAuth "Connect" button.
- `VERCEL_CLIENT_ID` / `VERCEL_CLIENT_SECRET` are no longer read or required; the per-server token is supplied at runtime through the Settings page.
- The OAuth callback no longer accepts `provider=vercel`. Stored credentials from the previous OAuth flow should be disconnected and reconnected with a fresh Vercel access token.

## New runtime tools

`VercelToolProvider` replaces the hosted-MCP wiring and exposes only the tools needed to publish a prototype:

- `vercel_list_projects(team_id?)` – `GET /v9/projects`
- `vercel_create_project(name, framework?, team_id?)` – `POST /v10/projects`
- `vercel_create_deployment(project_name, files, target?, team_id?)` – `POST /v13/deployments` with inline files; auto-creates the project on first deploy and returns the deployment record (the `url` and `alias` entries are normalized to `https://...`).

All requests authenticate with `Authorization: Bearer <access_token>` and translate transport/HTTP errors into a `RuntimeError` so failures surface inside the agent toolset as a clean error rather than leaking provider exceptions.

## Product designer flow

The product designer demo flow now builds a minimal `index.html` from the prototype summary and passes it as the deployment's `files` payload, so the live deployment URL actually serves something. Tool name and call shape stay backward compatible with the existing fakes used in agent tests.

## Tests

- `test_provider_registry.py` asserts the new Vercel `api_key` registration including the help URL.
- `test_runtime_providers.py` adds REST-level coverage for `VercelToolProvider` (auth header, team-id query param, project create body, inline file deployment, missing-token / empty-files / HTTP error paths) using `httpx.MockTransport`.
- `test_settings.py` no longer expects `VERCEL_CLIENT_ID/SECRET` env vars.
- `test_oauth_provider.py` and `test_connections.py` drop the Vercel hosted-MCP OAuth tests; the host-fallback flow test is rewritten against Notion (the remaining hosted-MCP provider).
- `ProviderCard.test.ts` swaps the example OAuth provider to GitHub so the generic OAuth UI assertions remain meaningful after Vercel switched to api_key.
