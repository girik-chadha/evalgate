from typing import Protocol

from evalgate.models import Assertion, Score


class Scorer(Protocol):
    async def score(self, input: str, output: str, assertion: Assertion) -> Score:
        """Judge `output`, the reply to `input`, against one assertion."""
        ...
