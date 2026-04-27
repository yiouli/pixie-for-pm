# Project Analysis

## What this software does

pixie-for-pm is a Discord-based product collaboration assistant that routes a user request through internal specialist agents such as a product manager, user researcher, and product designer, then returns a single public reply back into the Discord thread. A successful run looks like a short, useful response in the thread while the underlying orchestration layer handles internal handoffs, integration-backed work, and private intermediate artifacts such as research synthesis, PRDs, and prototype summaries.

## Target users and value proposition

The primary users are product teams operating through Discord, especially PM-led workflows that need quick cross-functional help without opening separate tools or coordinating by hand. The value proposition is that Pixie can turn a single conversational request into a coordinated internal workflow across research, product, and design roles, while also using connected tools such as Notion and Vercel to store longer-form work and produce deliverables. Quality here means the conversation stays concise and natural for the end user while the internal agent loop still performs the right specialist work, handoffs, and artifact creation.

## Capability inventory

1. Discord request intake and threaded reply handling: accepts direct mentions and replies to prior bot messages, then preserves the conversation in a Discord thread.
2. Dispatcher-led specialist routing: selects the appropriate internal agent, defaults ambiguous product work to the PM, and keeps specialist handoffs private.
3. PM-led multi-agent orchestration: the product manager can delegate work to the user researcher, receive findings back, and continue the user-facing response.
4. Research synthesis with integration-backed context: the user researcher can pull context from Notion and return a compact internal synthesis for downstream planning.
5. PRD and prototype workflow: the PM can draft a PRD for a chosen direction, hand it to the product designer, and receive a clickable prototype summary for the final user reply.
6. Integration-backed artifact delivery: the system can use connected providers such as Notion, GitHub, Vercel, and PostHog to create or retrieve supporting artifacts instead of forcing all content into chat.

## Realistic input characteristics

Real inputs are open-ended, multi-turn product requests written in conversational Slack- or Discord-style language, usually one to four short sentences per message but often underspecified. The app must handle two key input shapes: initial broad product questions such as low retention or weak adoption, and follow-up turns that reference prior options implicitly, for example “go deeper on #2.” Conversation state matters because the second turn depends on prior PM output and internal handoff context. External context can include long-form research notes, meeting notes, or synthesis artifacts stored in Notion, plus prototype deliverables and URLs from Vercel. The realistic scale ranges from short user messages under 200 characters to internal artifacts spanning hundreds or thousands of words, with variation in clarity, missing detail, and reference resolution across turns.

## Hard problems and failure modes

1. Incorrect internal handoff sequencing: the system may respond directly when it should delegate to the user researcher first, or fail to hand off the deep-dive flow from PM to product designer.
2. Leakage of internal working content into the public thread: long planning notes, full PRDs, or prototype briefs can be emitted as chat messages instead of being stored through tools and summarized back to the user.
3. Weak specialist outcomes despite correct routing: an agent may hand off to the right role but return the wrong artifact shape, such as hypotheses that are not distinct, a PRD that ignores the required structure, or a prototype summary that does not describe a clickable design outcome.
4. Missing or low-quality tool usage: the system may skip the tool-backed artifact workflow entirely, fail to call the right tool for Notion or Vercel, or generate the wrong content inside those tool calls.
5. Poor conversational UX in the final thread: messages can become overly long, list-heavy, and non-conversational, which breaks the product contract even if the internal work is mostly correct.
