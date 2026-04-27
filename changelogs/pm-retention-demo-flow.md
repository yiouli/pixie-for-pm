# PM Retention Demo Flow

## What Changed

- added a PM-led retention demo workflow that keeps the initial dispatch on the product manager, delegates research to the user researcher, and returns with three build hypotheses before asking for feedback
- updated the first PM retention-demo turn so the PM explains its reasoning and planned steps before handing the research pass to the user researcher
- fixed Discord delivery so that mid-turn PM planning notes are published immediately instead of being hidden behind later streamed output, and internal researcher/designer handoff work no longer streams to the user-facing reply
- added a follow-up deep-dive path where the PM drafts a Lenny Rachitsky-style PRD internally, hands it to the product designer, and returns with a review-ready prototype summary
- added a real product designer deep-agent handler and wired it into the default registry and Discord runtime
- threaded private handoff context through the orchestration graph so delegated agents can pass internal artifacts back to the PM without exposing them in the public reply
- tightened dispatcher keyword matching so short keywords like `ui` and `ux` no longer match unrelated words such as `build`

## Validation

- `uv run pytest web/tests/pixie_for_pm/agents/test_registry.py web/tests/pixie_for_pm/orchestration/test_runtime.py`
