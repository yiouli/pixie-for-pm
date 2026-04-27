from collections.abc import Callable
from typing import TypeVar, overload

_T = TypeVar("_T")

@overload
def wrap(
    value: _T,
    *,
    purpose: str,
    name: str,
    description: str,
) -> _T: ...
@overload
def wrap(
    value: Callable[[], _T],
    *,
    purpose: str,
    name: str,
    description: str,
) -> Callable[[], _T]: ...
