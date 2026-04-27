# Eval Criteria

## Use cases

1. Retention discovery handoff, routine: a user asks what to build next to improve low retention, and Pixie routes through the coordinator to user researcher, then to PM, then returns exactly three distinct hypotheses with a recommendation on which one to deepen.
2. Retention deep dive with design handoff, challenging: a user asks to go deeper on a numbered option from the prior coordinator reply, and Pixie creates the PRD as an internal artifact, hands it to the product designer through the coordinator, then returns a short review-ready prototype summary.
3. Integration-backed artifact workflow, challenging: when Notion and Vercel are connected, Pixie stores long-form research and PRD/prototype work through tools instead of posting those documents directly in the thread.

## Eval criteria

1. Demo handoff contract.
   Applies to: use cases 1 and 2.
   Criterion: the coordinator starts, the user researcher handles the evidence pass, the PM synthesizes options, and the coordinator owns all subsequent handoffs including the designer handoff.
   Data to capture: `handoff_sequence_*` wraps.
2. Research-to-PM usefulness.
   Applies to: use case 1.
   Criterion: the researcher output should be useful internal input for the PM rather than a generic summary or direct user-facing answer.
   Data to capture: `research_artifact` wraps and PM-facing handoff payloads.
3. First-turn option quality.
   Applies to: use case 1.
   Criterion: the first coordinator-visible outcome should present exactly three distinct next-build hypotheses, each with a short proposal, then ask which option to deepen.
   Data to capture: `public_reply_*` wraps for the first visible turn.
4. PRD persistence contract.
   Applies to: use cases 2 and 3.
   Criterion: the PM should write a substantive Lenny-style PRD to Notion instead of dumping the document body into the public thread.
   Data to capture: `prd_artifact`, `tool_args__*`, and `public_reply_*` wraps.
5. PRD artifact surfacing.
   Applies to: use case 2.
   Criterion: after the PRD write succeeds, the coordinator should surface a usable Notion link in the public reply and ask about the prototype next step.
   Data to capture: `public_reply_*` wraps and Notion tool-call outputs.
6. Designer handoff and publication.
   Applies to: use cases 2 and 3.
   Criterion: the designer should receive the PRD through the coordinator, publish or attempt to publish a clickable prototype through Vercel, and return the result to the coordinator.
   Data to capture: `prototype_artifact`, `handoff_sequence_*`, and `tool_args__*` wraps.
7. Prototype artifact surfacing.
   Applies to: use case 2.
   Criterion: the final coordinator-visible reply should include the deploy result and a usable Vercel URL when a deploy succeeds.
   Data to capture: `public_reply_*` wraps and Vercel tool-call outputs.
8. Public-thread brevity.
   Applies to: all use cases.
   Criterion: user-visible replies should stay short and conversational rather than containing plan dumps, PRD bodies, or prototype specs.
   Data to capture: `public_reply_*` wraps.

## Capability coverage

Capabilities covered: Discord request intake and threaded replies, coordinator-led multi-agent orchestration, research synthesis handoff, PRD-to-design prototype workflow, integration-backed artifact delivery.

Capabilities skipped (with rationale): market analyst behavior, settings/install web flows, and general non-demo prompts; this eval is intentionally scoped to the one retention demo scenario in `demo.md` rather than the full product surface.
