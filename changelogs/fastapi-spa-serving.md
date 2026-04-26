# FastAPI SPA Serving

- changed the settings frontend deployment model so FastAPI now serves the built Vite SPA directly from `web/dist`
- added SPA fallback behavior for client-side routes while preserving `/api/*` and `/healthz` backend handling
- added a `npm run watch` workflow that continuously rebuilds the frontend bundle into `dist` for local development
- updated the frontend API client to default to the current browser origin when `VITE_API_URL` is unset
- updated README, specs, and environment examples to document the single-server local development flow
