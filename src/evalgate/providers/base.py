from typing import Any, Protocol


class ProviderError(Exception):
    """A provider call failed.

    `retryable` is the provider's classification: timeouts, rate limits and
    server errors are worth another attempt; bad requests and bad keys are not.
    `retry_after_s` carries the server's Retry-After hint when it sent one.
    """

    def __init__(
        self,
        message: str,
        *,
        retryable: bool = True,
        retry_after_s: float | None = None,
    ) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.retry_after_s = retry_after_s


class Provider(Protocol):
    @property
    def model(self) -> str: ...

    async def complete(
        self, prompt: str, *, response_schema: dict[str, Any] | None = None
    ) -> str:
        """Return the model's text reply.

        `response_schema` is a JSON schema the reply must conform to. Providers
        that cannot enforce it may ignore it.
        """
        ...
