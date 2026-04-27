# Evaluator Mapping

## Built-in evaluators used

None. This scenario is centered on routing, artifact persistence, tool-use content, and conversational shape rather than comparison against a single reference answer.

## Agent evaluators

None in the current version. The retention demo is scored entirely with mechanical evaluators because the contract is mostly about routing, tool usage, artifact persistence, and public-link surfacing.

## Manual custom evaluators (mechanical checks only)

1. `pixie_qa/evaluators.py:notion_write_with_substantive_body`
   Criterion: the PM persists a substantive PRD to Notion through a real write tool.
   Applies to: all items.
2. `pixie_qa/evaluators.py:notion_link_surfaced_in_reply`
   Criterion: the public PRD reply includes a usable Notion link.
   Applies to: all items.
3. `pixie_qa/evaluators.py:designer_handoff_occurred`
   Criterion: the coordinator-led flow reaches the product designer after the prototype approval step.
   Applies to: all items.
4. `pixie_qa/evaluators.py:vercel_deployment_published`
   Criterion: a Vercel deploy-capable tool is actually called.
   Applies to: all items.
5. `pixie_qa/evaluators.py:vercel_link_surfaced_in_reply`
   Criterion: the final public reply includes a usable Vercel deployment URL.
   Applies to: all items.
6. `pixie_qa/evaluators.py:no_long_message_dump`
   Criterion: all public replies stay under the message-length guardrail and avoid dumping long artifacts into chat.
   Applies to: all items.
7. `pixie_qa/evaluators.py:conversation_has_three_distinct_turns`
   Criterion: the conversation follows the expected three-turn demo shape of options, PRD handoff, and prototype handoff.
   Applies to: all items.

## Applicability summary

- **Dataset-level defaults**: `pixie_qa/evaluators.py:notion_write_with_substantive_body`, `pixie_qa/evaluators.py:notion_link_surfaced_in_reply`, `pixie_qa/evaluators.py:designer_handoff_occurred`, `pixie_qa/evaluators.py:vercel_deployment_published`, `pixie_qa/evaluators.py:vercel_link_surfaced_in_reply`, `pixie_qa/evaluators.py:no_long_message_dump`, `pixie_qa/evaluators.py:conversation_has_three_distinct_turns`
- **Item-specific**: none for this first version; every dataset item is the same retention demo workflow and should satisfy the same contract.
