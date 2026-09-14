from typing import Protocol


class ProviderError(Exception):
    """Transient failure the runner may retry: timeout, rate limit, 5xx."""


class Provider(Protocol):
    model: str

    async def complete(self, prompt: str) -> str: ...
