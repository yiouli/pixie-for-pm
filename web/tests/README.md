# Test Layout

Tests mirror the source tree under `pixie_for_pm/`.

- `tests/pixie_for_pm/discord/` covers routing and Discord-side normalization helpers.
- `tests/pixie_for_pm/config/` covers environment-backed settings loading.
- `tests/pixie_for_pm/web/` covers auth, server claiming, connection CRUD, OAuth callback handling, and the internal credential API.
- `tests/pixie_for_pm/integrations/` covers provider registry metadata and the shared credential accessor used by integration helpers.
- `tests/pixie_for_pm/orchestration/` covers LangGraph execution, checkpoint creation, and handoff flow.
- `tests/pixie_for_pm/agents/` covers the Deep Agents-backed product manager handler and the remaining placeholder handler contract for the other internal roles.
