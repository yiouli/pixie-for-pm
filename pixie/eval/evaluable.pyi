from collections.abc import Mapping, Sequence
from typing import Any

class NamedData:
    name: str
    value: Any

    def __init__(self, *, name: str, value: Any) -> None: ...

class Evaluable:
    eval_input: list[NamedData]
    expectation: Any
    eval_metadata: dict[str, Any] | None
    description: str | None
    eval_output: list[NamedData]

    def __init__(
        self,
        *,
        eval_input: Sequence[NamedData | Mapping[str, Any]] = ...,
        expectation: Any = ...,
        eval_metadata: dict[str, Any] | None = ...,
        description: str | None = ...,
        eval_output: Sequence[NamedData | Mapping[str, Any]] = ...,
    ) -> None: ...
