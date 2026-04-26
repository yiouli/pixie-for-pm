# Single Bot Discord Surface

- removed per-agent Discord persona configuration from the runtime and `.env.example`
- simplified Discord routing so public work enters through one bot identity via direct mention, reply-to-bot, or slash command
- stopped surfacing internal LangGraph handoffs as synthetic Discord messages
- switched the `/settings` command to deferred interaction replies with `edit_original_response`
- updated README, specs, e2e docs, and install copy to describe the single-bot public model
