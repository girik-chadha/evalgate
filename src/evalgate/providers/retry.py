from typing import Any

import anyio

from evalgate.providers.base import Provider, ProviderError


class RetryingProvider:
    """Retries retryable ProviderErrors with exponential backoff.

    Total attempts are `retries + 1`. The server's Retry-After hint wins over
    the computed backoff when it is longer.
    """

    def __init__(
        self, inner: Provider, *, retries: int = 2, backoff_s: float = 0.5
    ) -> None:
        self._inner = inner
        self._retries = retries
        self._backoff_s = backoff_s

    @property
    def model(self) -> str:
        return self._inner.model

    async def complete(
        self, prompt: str, *, response_schema: dict[str, Any] | None = None
    ) -> str:
        for attempt in range(self._retries):
            try:
                return await self._inner.complete(
                    prompt, response_schema=response_schema
                )
            except ProviderError as e:
                if not e.retryable:
                    raise
                backoff = self._backoff_s * 2**attempt
                await anyio.sleep(max(backoff, e.retry_after_s or 0.0))
        return await self._inner.complete(prompt, response_schema=response_schema)
