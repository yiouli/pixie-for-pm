# Coordinator-only streaming

## Summary

- stop the product manager agent from streaming raw model deltas directly to Discord while it is still assembling an internal handoff for the coordinator
- preserve the existing coordinator handoff flow so the coordinator remains the only agent that turns specialist work into user-visible replies
- add regression coverage for both the generic PM path and the retention-demo option-summary path

## Validation

- `uv run pytest web/tests/pixie_for_pm/agents/test_registry.py -k "product_manager_handler_does_not_emit_streamed_content_deltas or product_manager_handler_does_not_stream_demo_option_summary"`
- `uv run pytest web/tests/pixie_for_pm/orchestration/test_runtime.py -k "retention_demo_discovery_and_deep_dive_flow"`
