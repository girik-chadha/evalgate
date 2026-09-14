from typing import Any

import anyio
import pytest

from evalgate.providers.base import ProviderError
from evalgate.providers.fake import FakeProvider
from evalgate.providers.retry import RetryingProvider


class StubProvider:
    model = "stub"

    def __init__(self, errors: list[ProviderError]) -> None:
        self._errors = list(errors)
        self.calls = 0

    async def complete(
        self, prompt: str, *, response_schema: dict[str, Any] | None = None
    ) -> str:
        self.calls += 1
        if self._errors:
            raise self._errors.pop(0)
        return "ok"


def complete(provider: RetryingProvider, **kwargs: Any) -> str:
    return anyio.run(lambda: provider.complete("prompt", **kwargs))


def test_retryable_errors_are_retried_until_success() -> None:
    inner = StubProvider([ProviderError("429"), ProviderError("500")])
    assert complete(RetryingProvider(inner, retries=2, backoff_s=0)) == "ok"
    assert inner.calls == 3


def test_gives_up_after_retries_and_raises_the_last_error() -> None:
    inner = StubProvider([ProviderError("first"), ProviderError("second")])
    with pytest.raises(ProviderError, match="second"):
        complete(RetryingProvider(inner, retries=1, backoff_s=0))
    assert inner.calls == 2


def test_non_retryable_errors_are_raised_immediately() -> None:
    inner = StubProvider([ProviderError("401", retryable=False)])
    with pytest.raises(ProviderError, match="401"):
        complete(RetryingProvider(inner, retries=3, backoff_s=0))
    assert inner.calls == 1


def test_retry_after_hint_extends_the_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    sleeps: list[float] = []

    async def record_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr("evalgate.providers.retry.anyio.sleep", record_sleep)
    inner = StubProvider(
        [ProviderError("429", retry_after_s=3.0), ProviderError("500")]
    )
    complete(RetryingProvider(inner, retries=2, backoff_s=0.5))
    assert sleeps == [3.0, 1.0]


def test_model_and_schema_pass_through() -> None:
    inner = FakeProvider({"prompt": "reply"})
    wrapped = RetryingProvider(inner)
    assert wrapped.model == "fake"
    assert complete(wrapped, response_schema={"type": "object"}) == "reply"
