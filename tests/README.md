# Test Layout

Tests mirror the source tree under `pixie_for_pm/`.

- `tests/discord-e2e.md` is the manual Discord end-to-end verification guide.
- `tests/pixie_for_pm/discord/` covers routing and Discord-side normalization helpers.
- `tests/pixie_for_pm/config/` covers environment-backed settings loading.
- `tests/pixie_for_pm/orchestration/` covers LangGraph execution, checkpoint creation, and handoff flow.
- `tests/pixie_for_pm/agents/` covers the hardcoded placeholder response contract used by the Discord e2e check.
