from typing import Protocol, Self, TypeVar

_WrappedT = TypeVar("_WrappedT")
_ArgsT = TypeVar("_ArgsT", contravariant=True)

def wrap(
    data: _WrappedT,
    *,
    purpose: str,
    name: str,
    description: str | None = ...,
) -> _WrappedT: ...

class Runnable(Protocol[_ArgsT]):
    @classmethod
    def create(cls) -> Self: ...
    async def setup(self) -> None: ...
    async def run(self, args: _ArgsT) -> None: ...
    async def teardown(self) -> None: ...
