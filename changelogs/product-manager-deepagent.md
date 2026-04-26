# Product Manager Deep Agent

- added a real product manager runtime built on LangChain Deep Agents
- configured the live PM path to use an OpenAI chat model, defaulting to `openai:gpt-5.4`
- kept the other internal roles on placeholder handlers so the public Discord surface changes only at the PM entrypoint
- added regression coverage for the PM handler and the orchestrator path using a tool-call-capable fake model
- updated manual e2e guidance and install copy to verify the public PM response with the `PM_AGENT_OK` marker
