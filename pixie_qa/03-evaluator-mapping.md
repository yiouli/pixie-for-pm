# Evaluator Mapping

## Built-in evaluators used

None. This scenario is centered on routing, artifact persistence, tool-use content, and conversational shape rather than comparison against a single reference answer.

## Agent evaluators

| Evaluator name                                         | Criterion it covers                                                                     | Applies to | Source file              |
| ------------------------------------------------------ | --------------------------------------------------------------------------------------- | ---------- | ------------------------ |
| `pixie_qa/evaluators.py:research_artifact_quality`     | The researcher outcome is PM-ready, grounded, and concise.                              | All items  | `pixie_qa/evaluators.py` |
| `pixie_qa/evaluators.py:first_turn_hypothesis_quality` | The first-turn PM outcome contains three distinct hypotheses with useful proposals.     | All items  | `pixie_qa/evaluators.py` |
| `pixie_qa/evaluators.py:prd_tool_call_quality`         | The PM saves a real Lenny-style PRD through tool content instead of dumping it in chat. | All items  | `pixie_qa/evaluators.py` |
| `pixie_qa/evaluators.py:prototype_handoff_quality`     | The deep-dive flow reaches design and yields a credible clickable-prototype handoff.    | All items  | `pixie_qa/evaluators.py` |
| `pixie_qa/evaluators.py:conversational_quality`        | The visible thread stays conversational and summary-oriented rather than memo-like.     | All items  | `pixie_qa/evaluators.py` |

## Manual custom evaluators (mechanical checks only)

| Evaluator name                                            | Criterion it covers                                                                                   | Applies to | Source file              |
| --------------------------------------------------------- | ----------------------------------------------------------------------------------------------------- | ---------- | ------------------------ |
| `pixie_qa/evaluators.py:demo_handoff_contract`            | The two-turn scenario follows the required PM/researcher/designer handoff sequence.                   | All items  | `pixie_qa/evaluators.py` |
| `pixie_qa/evaluators.py:three_hypotheses_shape`           | The first-turn reply structurally contains exactly three numbered options and a deepen-next question. | All items  | `pixie_qa/evaluators.py` |
| `pixie_qa/evaluators.py:tool_persistence_contract`        | The run performs Notion reads, Notion write-back, and a Vercel deployment, including a PRD write.     | All items  | `pixie_qa/evaluators.py` |
| `pixie_qa/evaluators.py:conversational_brevity_guardrail` | User-visible thread messages stay below the brevity thresholds and avoid plan-dump phrasing.          | All items  | `pixie_qa/evaluators.py` |

## Applicability summary

- **Dataset-level defaults**: `pixie_qa/evaluators.py:demo_handoff_contract`, `pixie_qa/evaluators.py:three_hypotheses_shape`, `pixie_qa/evaluators.py:tool_persistence_contract`, `pixie_qa/evaluators.py:conversational_brevity_guardrail`, `pixie_qa/evaluators.py:research_artifact_quality`, `pixie_qa/evaluators.py:first_turn_hypothesis_quality`, `pixie_qa/evaluators.py:prd_tool_call_quality`, `pixie_qa/evaluators.py:prototype_handoff_quality`, `pixie_qa/evaluators.py:conversational_quality`
- **Item-specific**: none for this first version; every dataset item is the same retention demo workflow and should satisfy the same contract.
