# Deep Agent Recursion Headroom

- raises deep-agent invocation recursion headroom from the LangGraph default to `100`
- adds structured logging around deep-agent start, completion, tool usage, and recursion-limit failures
- adds regression coverage to ensure both `ainvoke` and `astream_events` runs receive the configured recursion limit

## Why

User researcher runs can legitimately perform a long sequence of MCP tool calls before producing a final answer. The default recursion ceiling was low enough that these tool-heavy runs could fail intermittently with `GraphRecursionError`, and the previous runtime logs were too thin to explain what the agent was doing when it failed.

## Validation

- `uv run pytest web/tests/pixie_for_pm/agents/test_deep_agent.py`
