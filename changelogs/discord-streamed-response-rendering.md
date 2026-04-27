# Discord streamed response rendering

## Summary

- flush streamed Discord replies at paragraph or sentence boundaries within the configured 500 character stream window
- stop duplicating status text outside the in-progress embed and delete the status message after successful completion
- refresh Discord typing immediately after each non-final status or streamed message send so the indicator stays visible during chunked runs
- render Markdown tables into fenced monospaced text blocks so Discord displays them readably
- remove the streamed transcript length warning path tied to the Discord message limit and keep Discord limit handling as a chunk-size cap only

## Validation

- `uv run pytest web/tests/pixie_for_pm/discord/test_bot.py -k 'progress_reporter' -x -q`
