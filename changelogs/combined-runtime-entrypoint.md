# Combined Runtime Entrypoint

- added a managed Discord runtime that starts and stops under the FastAPI lifespan when running `uv run pixie`
- added a top-level `pixie` CLI for the combined long-lived server mode
- added `api/index.py` as the Vercel ASGI entrypoint so deployment imports the web app without booting the Discord gateway client
- kept `pixie-web-server` and `pixie-discord-bot` available for web-only and bot-only workflows
- added regression tests for FastAPI lifespan startup and the new CLI dispatch path
