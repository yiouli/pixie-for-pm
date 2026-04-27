# Discord Thread-First Replies

## Summary

- route direct mentions and legacy reply-to-bot messages into a Discord thread before Pixie sends its first status or final reply
- attach the created thread id to the dispatch request so orchestration state stays scoped to the thread instead of the parent channel message
- cover the new thread-first behavior with Discord bot regression tests for direct mentions, reply-to-bot fallbacks, and failure handling
- sanitize thread titles so new Pixie threads use concise request-based names instead of the raw mention text
- split long Discord replies at natural boundaries and continue them across follow-up messages with a trailing `[TBC]` marker on non-final chunks
- enforce Discord's real 2000-character message limit when editing or sending reply chunks so long answers do not fail at publish time
- style failure responses with a red Discord embed and fall back to `typing()` when `trigger_typing()` is unavailable on the response target
- render in-progress status updates as an orange Discord embed so working-state messages are visually distinct from final answers
- use a temporary `(cont.)` marker for partial chunks and remove it from the prior message once the next continuation message is sent
- propagate internal product-manager model lifecycle events into Discord status updates so long-running turns advance beyond the initial agent-routing message
- stream product-manager content deltas into Discord during generation, flushing partial message edits roughly every 500 characters and rolling over to a follow-up message immediately when a chunk hits Discord's limit

## Why

Pixie was mixing channel replies and thread replies depending on how a conversation started. That made follow-up behavior inconsistent and could split a single conversation across different Discord contexts.

## Validation

- `uv run pytest web/tests/pixie_for_pm/discord/test_bot.py`
- `uv run ruff check pixie_for_pm/discord/bot.py web/tests/pixie_for_pm/discord/test_bot.py`
- `uv run mypy pixie_for_pm/discord/bot.py web/tests/pixie_for_pm/discord/test_bot.py`
