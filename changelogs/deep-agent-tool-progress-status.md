# What Changed

- updated the shared deep-agent status mapper so tool execution now emits progress updates on `on_tool_start` and `on_tool_end`
- this keeps long-running user researcher and product designer runs from sitting on a stale `is reasoning...` status while integrations are actively running
- added regression coverage for product manager, user researcher, and product designer tool-progress status text

## Validation

- `uv run pytest web/tests/pixie_for_pm/agents/test_deep_agent.py`
- `uv run pytest web/tests/pixie_for_pm/agents/test_registry.py web/tests/pixie_for_pm/agents/test_deep_agent.py`
- `uv run ruff check .`
- `uv run mypy .`
