# User Researcher Loop Limit Regression

- restores the deep-agent recursion headroom config in the shared wrapper
- applies the same recursion limit to both `ainvoke` and streamed `astream_events` execution paths
- adds regression coverage so tool-heavy user researcher runs do not silently fall back to the default loop cap again

## Why

User researcher runs rely on the shared deep-agent wrapper and can execute long Notion-heavy tool chains. A regression removed the explicit recursion-limit config, which sent those runs back to the default LangGraph loop ceiling and caused them to fail before completion.

## Validation

- `uv run pytest web/tests/pixie_for_pm/agents/test_deep_agent.py`
