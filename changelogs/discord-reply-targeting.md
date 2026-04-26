# Discord Reply Targeting

## Summary

- fixed Discord reply-triggered agent responses so they use the source message reply path when no thread exists
- preserved existing behavior for thread replies by continuing to post back into the referenced thread

## Validation

- added a regression test covering replies to a bot message in a regular channel
- verified the focused Discord bot tests pass
