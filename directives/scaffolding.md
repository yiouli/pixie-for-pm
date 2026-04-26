# Project Scaffolding

let's setup the scaffolding for the project now.

The system would be a multi-agent system internally, while work is triggered by a single Discord bot in a particular server.

we're going to have 5 different agents:

- product manager: create product concept, JTBD, product vision/mission, PRD drafting etc
- market analyst: compatitive analysis, market sizing, industry trend etc
- user researcher: interview design, interview sythethization etc
- data scientist: product data analytics
- product designer: product mocking

Discord should expose one public bot identity. Work starts when a user mentions the bot, replies to a prior bot message, or runs a slash command. The product manager should remain the entrypoint agent and delegate internally as needed.

Each agent should still be able to hand off work internally through the orchestration framework, but those handoffs should not appear as separate Discord personas or synthetic agent-to-agent messages. If a slash-command flow needs progress updates, use deferred interaction replies and edits instead.

We are going to use Langgraph as the orchestration. We'd need to have proper persistant execution feature eanbled. For now let's have a empty placeholder function for each of the agent.

For scaffolding, please setup the discord intergration with the langgraph orchestration, with placeholder agent functions for now. Create a .env.example file to include configurations for the scaffolding, and also create a readme to explain the architecture.
