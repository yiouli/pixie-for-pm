# Retention Demo Artifact Contract

- Fixed PM PRD replies so hosted Notion MCP responses with bare page identifiers are normalized into public Notion URLs before the coordinator surfaces them.
- Fixed the designer publish path to discover alternate Vercel deploy tools, extract real `.vercel.app` URLs when available, and return a blocked/advisory artifact instead of a false success when the runtime only provides manual deploy instructions.
- Fixed the coordinator prototype reply handling so blocked designer outcomes are surfaced honestly instead of being rewritten into `prototype draft is ready`.
- Updated the retention-demo dataset to include explicit hosted Notion/Vercel tool fixtures for the happy path.
- Split the three-turn evaluator from the link-specific checks so future eval failures localize to conversation shape versus artifact-link surfacing.
- Added focused regressions for Notion URL normalization, manual-deploy honesty, coordinator blocked-reply handling, end-to-end artifact links, and the evaluator split.
