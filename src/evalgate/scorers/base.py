from typing import Protocol

from evalgate.models import Assertion, Score


class Scorer(Protocol):
    async def score(self, output: str, assertion: Assertion) -> Score: ...
