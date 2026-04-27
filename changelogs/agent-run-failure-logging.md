# Agent Run Failure Logging

## What Changed

- added structured exception logging around deep-agent execution so failed runs now emit the agent role, agent name, thread key, Discord routing context, connected integrations, and any integration initialization failures
- added request-level dispatch failure logging in the orchestrator so agent crashes can be correlated back to the Discord server, channel, message, and target agent that triggered the run
- added wrapped tool invocation logging in the integration toolset so MCP or provider failures now record the provider, tool name, request routing context, and supplied argument keys before re-raising
- added regression coverage for deep-agent, wrapped tool, and orchestration failure logging
- investigated the Notion `update_content` validation failure and added a one-shot deep-agent retry when a tool error reports a missing required parameter, along with a user researcher execution-context hint that `update_content` must include `content_updates`
- changed the validation-error retry path to create a fresh deep-agent instance for the retry attempt instead of reusing the failed one
- removed the duplicate immediate PM retention handoff publish and dropped the low-value `Starting point:` echo so the first Discord message is sent once and no longer repeats the user's prompt verbatim

## Validation

- `uv run pytest web/tests/pixie_for_pm/agents/test_deep_agent.py web/tests/pixie_for_pm/integrations/test_toolset.py web/tests/pixie_for_pm/orchestration/test_runtime.py -k 'logs_failure_context or logs_runtime_failures or logs_dispatch_failures'`
- `uv run pytest web/tests/pixie_for_pm/agents/test_deep_agent.py web/tests/pixie_for_pm/agents/test_registry.py web/tests/pixie_for_pm/orchestration/test_runtime.py web/tests/pixie_for_pm/discord/test_bot.py -k 'retention_demo_discovery_and_deep_dive_flow or publishes_mid_turn_message_without_replaying_it_at_completion or retries_tool_validation_errors or recreates_agent_for_validation_retry or delegates_demo_retention_questions_to_user_researcher'`
