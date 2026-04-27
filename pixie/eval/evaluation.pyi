from typing import Any

class Evaluation:
    score: float
    reasoning: str
    details: dict[str, Any]

    def __init__(
        self,
        score: float,
        reasoning: str,
        details: dict[str, Any] = ...,
    ) -> None: ...
