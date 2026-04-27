# User Researcher Agent

## Summary

- added a LangGraph-backed user researcher agent
- required an active Notion integration before the user researcher workflow runs
- instructed the agent to read product and user research context from Notion, follow the interview synthesis handbook, and write tagging plus final synthesis artifacts back to Notion

## Code Changes

- extracted shared deep-agent execution helpers so multiple specialist agents can reuse the same LangGraph streaming and status plumbing
- implemented `pixie_for_pm/agents/user_researcher.py` with a handbook-driven system prompt and Notion-aware execution context
- wired the user researcher into registry defaults and the Discord bot runtime
- added dispatcher and orchestration regression coverage for researcher routing

## Validation

- `uv run pytest web/tests/pixie_for_pm/agents/test_registry.py`
- `uv run pytest web/tests/pixie_for_pm/orchestration/test_runtime.py`
