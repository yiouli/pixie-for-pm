# Coordinator-authored demo replies

## Summary

- move retention-demo user-facing reply generation into the coordinator so Discord-visible wording is no longer assembled inside the product manager or product designer handlers
- change the product manager demo handoff to return structured artifacts for option summaries and PRD readiness instead of hardcoded final reply strings
- keep coordinator streaming enabled while suppressing raw specialist draft streaming, so Discord now shows coordinator-authored text rather than PM `Idea/Why/Proposal` blocks
- widen the option-selection and prototype-approval parsing heuristics so they continue to work with coordinator-generated wording rather than one exact canned phrase

## Validation

- `uv run pytest web/tests/pixie_for_pm/agents/test_registry.py`
- `uv run pytest web/tests/pixie_for_pm/orchestration/test_runtime.py -k "retention_demo_discovery_and_deep_dive_flow or retention_demo_does_not_stream_specialist_drafts"`
- `uv run ruff check pixie_for_pm/agents/demo_flow.py pixie_for_pm/agents/dispatcher.py pixie_for_pm/agents/product_manager.py web/tests/pixie_for_pm/agents/test_registry.py web/tests/pixie_for_pm/orchestration/test_runtime.py`
- `uv run mypy pixie_for_pm/agents/demo_flow.py pixie_for_pm/agents/dispatcher.py pixie_for_pm/agents/product_manager.py`
