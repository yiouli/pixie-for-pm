# Notion Runtime Failure Messaging

## What Changed

- preserved integration initialization failures in the request-scoped toolset instead of silently dropping them
- updated the user researcher preflight to distinguish between a missing Notion connection and a connected Notion integration whose runtime initialization failed
- replaced the generic Notion API OAuth flow with Notion MCP discovery, dynamic client registration, and PKCE so new Notion connections produce MCP-compatible tokens
- added regression coverage for both the toolset failure record and the user-facing Notion reconnect message
- added route and provider tests for the Notion MCP authorize and callback flow

## Operator Note

- existing Notion connections created before this change should be disconnected and reconnected so Pixie stores MCP-native tokens instead of the old generic Notion API tokens

## Validation

- `uv run pytest web/tests/pixie_for_pm/integrations/test_toolset.py web/tests/pixie_for_pm/agents/test_registry.py`
