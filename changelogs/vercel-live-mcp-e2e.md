# Live Vercel MCP E2E

## What Changed

- added a no-LLM live pytest at `web/tests/e2e/test_live_vercel_mcp_tools.py` that initializes the real request-scoped toolset for Discord server `1459772566528069715`, asserts the expected Vercel MCP tools are present, creates a disposable minimal Next.js app, and then exercises the live Vercel discovery and deploy tools directly
- gated the live test behind `PIXIE_RUN_LIVE_VERCEL_MCP_E2E=1` so the normal suite stays green while still allowing explicit re-runs against the real connected server
- made the live harness pin the connection-store and checkpoint paths to absolute paths so changing into the disposable app directory does not break the SQLite-backed runtime context during tool invocation
- updated the live harness to follow the current Vercel REST tool contract by asserting `vercel_list_projects`, `vercel_create_project`, and `vercel_create_deployment`, creating a unique Next.js project name per run, and uploading the app files inline instead of relying on the removed CLI-style deploy helper
- strengthened deployment verification by polling the authenticated Vercel deployment record until it reaches `READY`, which matches the live workspace policy because this team protects `.vercel.app` domains with SSO and anonymous page fetches return `401 Authentication Required`
- updated the Vercel runtime provider to send `public: true` on inline deployments because the live API defaults to `public: false`, which caused the returned `.vercel.app` URL to require Vercel authentication and broke anonymous end-to-end verification
- captured the remaining live constraint from the connected workspace: even with `public: true`, the team reports `ssoProtection.deploymentType = all_except_custom_domains`, so end-to-end verification must use the authenticated deployment API rather than an unauthenticated page fetch
- refreshed the disposable Next.js fixture to `next@16.2.4`, `react@19.2.5`, and `react-dom@19.2.5` after the live Vercel API started rejecting the earlier pinned sample app with `VULNERABLE_NEXTJS_VERSION`
- added authenticated teardown for the disposable Vercel project created by the live e2e so each run deletes its unique project id in a `finally` path, preventing the verification harness from leaving server-scoped test projects behind on success or failure
- manually verified the current live MCP surface for this server and confirmed two blockers:
  - `vercel_list_teams` returns `403 Forbidden`, which prevents the no-LLM discovery path from obtaining a team id for `vercel_list_projects`
  - `vercel_deploy_to_vercel` does not return a deployed `.vercel.app` URL for a disposable Next.js app and instead only returns CLI guidance to run `vercel deploy`

## Validation

- `uv run pytest web/tests/e2e/test_live_vercel_mcp_tools.py`
- `PIXIE_RUN_LIVE_VERCEL_MCP_E2E=1 uv run pytest web/tests/e2e/test_live_vercel_mcp_tools.py`
  Observed failure: `vercel_list_teams` returned `403 Forbidden`, and `vercel_deploy_to_vercel` returned CLI instructions instead of a live deployment URL.
- `uv run ruff check web/tests/e2e/test_live_vercel_mcp_tools.py`
