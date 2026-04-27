# Coordinator kickoff replies no longer stream

## Summary

- stop the coordinator from streaming its interim "kickoff" replies (the short
  acknowledgements emitted before handing off to a specialist) through the
  Discord response stream emitter
- these kickoff replies still reach Discord as standalone messages via the
  public message emitter, but they no longer set `_has_stream_activity` on the
  Discord progress reporter
- this restores per-specialist status updates ("User researcher is
  reasoning...", etc.) which were being suppressed once the kickoff text was
  streamed, and prevents the kickoff text from being concatenated onto the
  coordinator's final reply in the same Discord stream message
- coordinator final replies (out-of-scope, generic handoff completion, demo
  success/blocked summaries) continue to stream as before

## Validation

- `uv run pytest web/tests/pixie_for_pm/orchestration/test_runtime.py -k "retention_demo_does_not_stream_specialist_drafts or retention_demo_discovery_and_deep_dive_flow or emits_internal_product_manager_status_updates"`
- `uv run ruff check pixie_for_pm/agents/dispatcher.py web/tests/pixie_for_pm/orchestration/test_runtime.py`
- `uv run mypy pixie_for_pm/agents/dispatcher.py`
