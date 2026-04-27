from __future__ import annotations

from pixie.eval.evaluable import Evaluable

from pixie_qa.evaluators import conversation_has_three_distinct_turns


def test_conversation_shape_is_independent_from_link_checks() -> None:
    evaluable = Evaluable(
        eval_input=[{"name": "input_data", "value": {}}],
        eval_output=[
            {
                "name": "public_reply_1001",
                "value": (
                    "1. Option one\n2. Option two\n3. Option three\n"
                    "Which option should I deepen next?"
                ),
            },
            {
                "name": "public_reply_1002",
                "value": "PRD for option #2 is ready. Want me to spin up a prototype next?",
            },
            {
                "name": "public_reply_1003",
                "value": "on it. I have a final prototype update ready.",
            },
        ],
        description="three-turn shape without link fixtures",
    )

    evaluation = conversation_has_three_distinct_turns(evaluable)

    assert evaluation.score == 1.0
