# Discord Invocation Responsiveness

## Summary

Mention- and reply-triggered Discord turns now acknowledge work immediately instead of staying silent until the final agent message is ready.

## What Changed

- the triggering Discord message now gets an immediate `:eyes:` reaction before orchestration starts
- the bot now creates a single editable placeholder reply and updates it with runtime progress states such as `Thinking...`, provider fetches, and handoffs while Discord's native typing indicator stays active in parallel
- orchestration now accepts an optional status emitter so LangGraph node starts and wrapped tool invocations can surface progress without changing checkpoint state
- wrapped integration tools now emit provider-specific progress messages before and after fetches
- dispatch failures now edit the placeholder into an explicit error status instead of leaving a stale in-progress state behind
- plain follow-up messages in a thread now continue the conversation after the bot has already participated in that thread

## Validation

- `uv run pytest web/tests/pixie_for_pm/discord/test_bot.py web/tests/pixie_for_pm/orchestration/test_runtime.py web/tests/pixie_for_pm/integrations/test_toolset.py`
