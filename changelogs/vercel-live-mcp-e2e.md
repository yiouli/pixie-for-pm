# Live Vercel MCP E2E

## What Changed

- added a no-LLM live pytest at `web/tests/e2e/test_live_vercel_mcp_tools.py` that initializes the real request-scoped toolset for Discord server `1459772566528069715`, asserts the expected Vercel MCP tools are present, creates a disposable minimal Next.js app, and then exercises the live Vercel discovery and deploy tools directly
- gated the live test behind `PIXIE_RUN_LIVE_VERCEL_MCP_E2E=1` so the normal suite stays green while still allowing explicit re-runs against the real connected server
- made the live harness pin the connection-store and checkpoint paths to absolute paths so changing into the disposable app directory does not break the SQLite-backed runtime context during tool invocation
- manually verified the current live MCP surface for this server and confirmed two blockers:
  - `vercel_list_teams` returns `403 Forbidden`, which prevents the no-LLM discovery path from obtaining a team id for `vercel_list_projects`
  - `vercel_deploy_to_vercel` does not return a deployed `.vercel.app` URL for a disposable Next.js app and instead only returns CLI guidance to run `vercel deploy`

## Validation

- `uv run pytest web/tests/e2e/test_live_vercel_mcp_tools.py`
- `PIXIE_RUN_LIVE_VERCEL_MCP_E2E=1 uv run pytest web/tests/e2e/test_live_vercel_mcp_tools.py`
  Observed failure: `vercel_list_teams` returned `403 Forbidden`, and `vercel_deploy_to_vercel` returned CLI instructions instead of a live deployment URL.
- `uv run ruff check web/tests/e2e/test_live_vercel_mcp_tools.py`
