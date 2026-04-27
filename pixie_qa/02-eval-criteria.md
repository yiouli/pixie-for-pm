# Eval Criteria

## Use cases

1. Retention discovery handoff, routine: a user asks what to build next to improve low retention, and Pixie routes through PM to user researcher, then returns exactly three distinct hypotheses with a recommendation on which one to deepen.
2. Retention deep dive with design handoff, challenging: a user asks to go deeper on a numbered option from the prior PM reply, and Pixie creates the PRD as an internal artifact, hands it to the product designer, then returns a short review-ready prototype summary.
3. Integration-backed artifact workflow, challenging: when Notion and Vercel are connected, Pixie stores long-form research and PRD/prototype work through tools instead of posting those documents directly in the thread.

## Eval criteria

| #   | Criterion                                                                                                                                                                                           | Applies to     | Data to capture                 |
| --- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------- | ------------------------------- |
| 1   | The agent sequence matches the demo contract: PM starts, researcher handles the evidence pass, PM synthesizes options, then PM hands deep-dive work to the product designer before the final reply. | Use cases 1, 2 | wrap name: `handoff_sequence`   |
| 2   | The researcher outcome is usable by PM: it reflects a retention barrier and leverage points rather than generic filler or a direct user-facing answer.                                              | Use case 1     | wrap name: `research_artifact`  |
| 3   | The first-turn PM outcome contains exactly three distinct next-build hypotheses, each with a short high-level proposal, and ends by asking which option to deepen.                                  | Use case 1     | wrap name: `public_reply`       |
| 4   | The deep-dive PM outcome creates a PRD artifact that follows the required Lenny-style structure and stays out of the public thread.                                                                 | Use case 2     | wrap name: `prd_artifact`       |
| 5   | The designer outcome reflects a prototype-producing handoff: it uses the PRD artifact, produces a clickable-prototype summary or publish result, and hands that back to PM.                         | Use case 2     | wrap name: `prototype_artifact` |
| 6   | Tool usage matches the workflow: Notion is used for long-form research and PRD persistence, and Vercel is used for prototype publication or update when available.                                  | Use cases 2, 3 | wrap name: `tool_calls`         |
| 7   | Tool-call content is fit for purpose: the saved PRD is concise, follows the requested PM template, and the persisted artifacts contain the long-form work that should not appear in chat.           | Use cases 2, 3 | wrap name: `artifact_payloads`  |
| 8   | Public thread messages stay conversational and short: they should be concise summaries or questions, not procedural plan dumps or full document write-ups.                                          | All            | wrap name: `thread_messages`    |

## Capability coverage

Capabilities covered: Discord request intake and threaded replies, PM-led multi-agent orchestration, research synthesis handoff, PRD-to-design prototype workflow, integration-backed artifact delivery.

Capabilities skipped (with rationale): market analyst behavior, settings/install web flows, and general non-demo prompts; this eval is intentionally scoped to the one retention demo scenario in `demo.md` rather than the full product surface.
