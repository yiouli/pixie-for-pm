# Retention demo PM deep-dive split into two turns

## Why

The retention-demo eval (`pixie_qa/results/20260427-091229`) showed the PM was
taking real-user replies like `2` (option pick) and `sure` (prototype approval)
and falling through to the generic deep-agent loop. The agent then dumped the
full PRD into Discord, never saved it to Notion, never linked an artifact, and
never handed off to the product designer. Six of seven mechanical evaluators
failed for the same root cause.

Step 6 analysis is in `pixie_qa/results/20260427-091229/dataset-0/analysis.md`
and the action plan in `pixie_qa/results/20260427-091229/action-plan.md`.

## Changes

### `pixie_for_pm/agents/demo_flow.py`

- New `parse_bare_option_choice(message, *, recent_pm_reply)` that matches `2`,
  `#2`, `option 2`, or `the second one` only when the most recent PM reply
  asked which option to deepen. Avoids hijacking unrelated numeric replies.
- New `parse_prototype_approval(message, *, recent_pm_reply)` that matches
  `sure`, `yes`, `go ahead`, `ok`, etc. only after the PM explicitly asked
  about spinning up a prototype. Rejects `no`-prefixed replies.
- New `AWAITING_PROTOTYPE_APPROVAL_STAGE` constant for future use.

### `pixie_for_pm/agents/product_manager.py`

- The deep-dive branch now splits across two user turns:
  1. **Turn N (option pick):** generate the PRD, persist it to Notion via the
     real hosted MCP write tool (`notion_notion-create-pages`, falling back to
     `update-page`), and reply with a one-line link plus the question
     `Want me to spin up a quick clickable prototype for it next?`.
  2. **Turn N+1 (approval):** detect the approval against the prior PM reply
     and hand off to the product designer with a brief that includes the
     Notion URL and prior PM message as the PRD reference.
- New helpers `_persist_prd_artifact`, `_extract_recent_pm_reply`,
  `_build_prd_reply`, `_build_designer_brief_from_history`,
  `_find_tool_by_fragments`, `_safe_invoke`, `_extract_notion_url`.

### `pixie_qa/evaluators.py`

- Tightened `notion_write_with_substantive_body`. A pass now requires the
  write body to contain a PRD/product-spec marker (`PRD`,
  `Problem statement`, `MVP`, `Goals`, `Solution overview`, etc.) in addition
  to being ≥ 80 words. Closes the false-positive where research-scratch page
  updates by the user-researcher were counted as a saved PRD.

### Tests

- New `web/tests/pixie_for_pm/agents/test_demo_flow.py` covering
  `parse_bare_option_choice` and `parse_prototype_approval`.
- Updated `test_registry.py` to assert the new two-turn deep-dive flow:
  the option-pick turn no longer hands off to the designer; a separate
  approval turn does. Added a third test for the approval handoff path.
- Updated `test_runtime.py::test_orchestrator_runs_retention_demo_discovery_and_deep_dive_flow`
  to drive a third user turn (`sure`) and assert the designer prototype
  summary now arrives on the third turn instead of the second.

## Validation

```bash
uv run pytest web/tests/pixie_for_pm/  # 141 + 18 new tests = 159 passed
uv run ruff format pixie_qa/evaluators.py pixie_for_pm/agents/{demo_flow,product_manager}.py
uv run ruff check pixie_qa/evaluators.py pixie_for_pm/agents/{demo_flow,product_manager}.py
```

Re-running the eval (`pixie test`) is the next step. Vercel reconnect
(Priority 3 from the action plan) is a user-side action and is not blocked by
this change.
