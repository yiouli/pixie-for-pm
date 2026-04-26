# Agent Runtime Toolset

- added a typed request-scoped integration tool initializer for Discord-triggered LangGraph turns
- propagated Discord guild and user identity into the runtime as a `DiscordTriggerContext`
- materialized connected provider catalogs as `langchain_core` tools in an `AgentToolset` that can be passed directly to LangGraph agents
- kept live tool objects out of checkpoint state by building the workflow graph with per-dispatch runtime context
- added regression tests for toolset initialization, tool invocation bookkeeping, and orchestrator context injection
