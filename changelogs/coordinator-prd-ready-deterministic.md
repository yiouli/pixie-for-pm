# Deterministic PRD-ready coordinator reply

## Summary

- stop the coordinator from authoring the retention-demo PRD-ready reply with
  an LLM call. When the prompt only contained the option number and a Notion
  URL, the model would dump a full PRD-shaped block back into Discord instead
  of the short `PRD ready: <notion url>. Want me to spin up a quick clickable
prototype?` the spec calls for
- the PRD-ready reply is now rendered deterministically from the structured
  artifact the product manager hands off (`option_number`, `page_url`,
  `persisted`), matching the pre-refactor wording
- options-summary, prototype-summary, kickoff acknowledgements, and other
  generic coordinator replies still go through the LLM as before
- updated the retention-demo orchestrator test to expect the deterministic PRD
  reply verbatim, and removed the stale fake LLM response that was being
  consumed by that turn

## Validation

- `uv run pytest web/tests/pixie_for_pm/orchestration/test_runtime.py::test_orchestrator_runs_retention_demo_discovery_and_deep_dive_flow web/tests/pixie_for_pm/orchestration/test_runtime.py::test_orchestrator_retention_demo_does_not_stream_specialist_drafts web/tests/pixie_for_pm/agents/test_registry.py`
- `uv run ruff check pixie_for_pm/agents/dispatcher.py web/tests/pixie_for_pm/orchestration/test_runtime.py`
- `uv run mypy pixie_for_pm/agents/dispatcher.py`
