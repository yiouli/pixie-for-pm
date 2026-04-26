# Project Scaffolding

let's setup the scaffolding for the project now.

The system would be a multi-agent system, while work is triggered by discord message in a particular server.

we're going to have 5 different agents:

- product manager: create product concept, JTBD, product vision/mission, PRD drafting etc
- market analyst: compatitive analysis, market sizing, industry trend etc
- user researcher: interview design, interview sythethization etc
- data scientist: product data analytics
- product designer: product mocking

each agent would map to a unique character (avatar) in discord, and work can be directly dispatched to the agent via @mention/reply to thread. Message without @mention or thread should be handled by the product manager to start and delegate as needed.

Each agent would also be able to handle-off/create work for other agent as needed. Each handoff should trigger discord messages to give the appearance that the handleoff is triggered by an agent @mention/respond to another agent, while the real-handleoff should happen within the orchestration framework.

We are going to use Langgraph as the orchestration. We'd need to have proper persistant execution feature eanbled. For now let's have a empty placeholder function for each of the agent.

For scaffolding, please setup the discord intergration with the langgraph orchestration, with placeholder agent functions for now. Create a .env.example file to include configurations for the scaffolding, and also create a readme to explain the architecture.
