# User Researcher MCP Artifact Wrapper

## What Changed

- fixed the integration tool wrapper so hosted MCP tools that use `content_and_artifact` keep returning the two-part `(content, artifact)` payload LangChain expects
- invoked wrapped MCP tools with a synthetic tool-call envelope so the wrapper can preserve both the display content and the raw artifact instead of collapsing the response to a bare list
- added a regression test covering wrapped `content_and_artifact` tools to prevent the user researcher Notion flow from failing at runtime

## Validation

- `uv run pytest web/tests/pixie_for_pm/integrations/test_toolset.py`
