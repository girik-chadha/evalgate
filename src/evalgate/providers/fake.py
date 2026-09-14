from collections.abc import Mapping
from pathlib import Path
from typing import Any, Self

import yaml

from evalgate.providers.base import ProviderError


class FakeProvider:
    """Answers with the response whose key is a substring of the prompt.

    `fail_first` makes the first N calls raise ProviderError, to exercise retries.
    """

    model = "fake"

    def __init__(
        self,
        responses: Mapping[str, str],
        *,
        default: str = "",
        fail_first: int = 0,
    ) -> None:
        self._responses = dict(responses)
        self._default = default
        self._fail_first = fail_first
        self.calls: list[str] = []

    @classmethod
    def from_file(cls, path: Path) -> Self:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in data.items()
        ):
            raise ValueError(f"{path}: expected a mapping of prompt substring to reply")
        return cls(data)

    async def complete(
        self, prompt: str, *, response_schema: dict[str, Any] | None = None
    ) -> str:
        self.calls.append(prompt)
        if len(self.calls) <= self._fail_first:
            raise ProviderError(f"simulated failure {len(self.calls)}")
        for needle, response in self._responses.items():
            if needle in prompt:
                return response
        return self._default
