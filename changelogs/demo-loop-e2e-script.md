# Demo Loop E2E Script

## What Changed

- added a dedicated Playwright e2e harness for the two-turn retention demo flow in [demo.md](/home/yiouli/repo/pixie-for-pm/demo.md)
- the harness starts a custom FastAPI test server that bypasses settings authentication, seeds the fixed Discord workspace `1459772566528069715`, and exposes a synthetic Discord dispatch route for the full agent loop
- the synthetic loop uses deterministic PM, user researcher, and product designer handlers so the test covers the full orchestration path without live Discord, Notion, or Vercel dependencies
- added a `npm run test:e2e:demo-loop` script and documented the workflow in the Discord e2e guide

## Validation

- `cd web && npm run test:e2e:demo-loop`
