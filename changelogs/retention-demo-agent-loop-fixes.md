# Retention Demo Agent Loop Fixes

## What Changed

- tightened the retention-demo PM handback so the public reply now emits the short three-option list from the demo flow and carries forward the saved research synthesis Notion link instead of publishing the model's longer internal rationale block
- hardened Notion URL extraction for PRD persistence so malformed tool responses with encoded JSON suffixes are normalized back to a canonical `https://www.notion.so/<page_id>` link
- moved the Notion fetch safety guidance into a shared deep-agent helper and applied it to the product designer as well as the user researcher, so both agents are told to search first and reuse canonical Notion identifiers instead of inventing locators
- changed prototype deployment to create a fresh thread-scoped Next.js Vercel project name for each retention-demo build and pass that explicit instruction into the deployment summary rather than reusing an existing project name from `vercel_list_projects`
- added regression coverage for the concise demo reply shape, malformed Notion URL cleanup, shared product-designer Notion guidance, and the fresh-project Vercel deployment contract

## Validation

- `uv run pytest web/tests/pixie_for_pm/agents/test_registry.py web/tests/pixie_for_pm/orchestration/test_runtime.py -k 'formats_demo_option_titles_and_research_link or strips_encoded_json_suffix or product_designer_execution_context_requires_search_before_fetch or publishes_demo_prototype_before_pm_handoff or marks_manual_vercel_deploy_as_blocked or retention_demo_discovery_and_deep_dive_flow'`
- `uv run pytest web/tests/pixie_for_pm/agents/test_deep_agent.py web/tests/pixie_for_pm/agents/test_registry.py web/tests/pixie_for_pm/orchestration/test_runtime.py`
- `uv run mypy pixie_for_pm/agents/deep_agent.py pixie_for_pm/agents/user_researcher.py pixie_for_pm/agents/product_manager.py pixie_for_pm/agents/product_designer.py`
- `uv run ruff check pixie_for_pm/agents/deep_agent.py pixie_for_pm/agents/user_researcher.py pixie_for_pm/agents/product_manager.py pixie_for_pm/agents/product_designer.py web/tests/pixie_for_pm/agents/test_registry.py web/tests/pixie_for_pm/orchestration/test_runtime.py`
