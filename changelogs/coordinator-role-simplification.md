# Coordinator Role Simplification

## Summary

Reworked the multi-agent runtime so the coordinator is the only role that talks to the user and the only role that chooses handoff destinations.

## What Changed

- Renamed the dispatcher role contract to coordinator semantics at the model and routing layers.
- Enforced coordinator-only handoff authority in the LangGraph validation layer.
- Changed product manager, user researcher, product designer, and placeholder handlers to return artifacts back to the coordinator instead of user-facing messages.
- Moved the retention demo flow to coordinator-owned routing: coordinator -> researcher -> coordinator -> PM -> coordinator -> designer -> coordinator.
- Expanded the coordinator routing logic to handle shorthand option-deepening requests as well as explicit PRD asks.

## Validation

- `uv run pytest web/tests/pixie_for_pm/discord/test_routing.py web/tests/pixie_for_pm/agents/test_registry.py web/tests/pixie_for_pm/orchestration/test_runtime.py`

## Follow-on Impact

- Runtime status streams now include coordinator return hops when specialists finish work.
- Public Discord transcripts now reflect coordinator messages rather than specialist messages.
