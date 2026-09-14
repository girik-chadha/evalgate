from typing import Any

import httpx

from evalgate.providers.base import ProviderError

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"
RETRYABLE_STATUSES = frozenset({408, 409, 429})


class AnthropicProvider:
    """Calls the Messages API directly over httpx.

    The client is injected so the caller owns its lifetime and tests can swap
    in a mock transport. `temperature` is omitted from the request unless set:
    current models reject it with a 400.
    """

    def __init__(
        self,
        model: str,
        api_key: str,
        client: httpx.AsyncClient,
        *,
        max_tokens: int = 16000,
        temperature: float | None = None,
    ) -> None:
        self._model = model
        self._client = client
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._headers = {"x-api-key": api_key, "anthropic-version": API_VERSION}

    @property
    def model(self) -> str:
        return self._model

    async def complete(
        self, prompt: str, *, response_schema: dict[str, Any] | None = None
    ) -> str:
        body: dict[str, Any] = {
            "model": self._model,
            "max_tokens": self._max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if self._temperature is not None:
            body["temperature"] = self._temperature
        if response_schema is not None:
            body["output_config"] = {
                "format": {"type": "json_schema", "schema": response_schema}
            }
        try:
            response = await self._client.post(
                API_URL, json=body, headers=self._headers
            )
        except httpx.TransportError as e:
            raise ProviderError(f"{type(e).__name__}: {e}") from e
        if response.status_code != 200:
            raise _status_error(response)
        content = response.json()["content"]
        return "".join(block["text"] for block in content if block["type"] == "text")


def _status_error(response: httpx.Response) -> ProviderError:
    status = response.status_code
    try:
        error = response.json()["error"]
        detail = f"{error['type']}: {error['message']}"
    except (ValueError, KeyError, TypeError):
        detail = response.text[:200]
    return ProviderError(
        f"HTTP {status} {detail}",
        retryable=status in RETRYABLE_STATUSES or status >= 500,
        retry_after_s=_retry_after(response),
    )


def _retry_after(response: httpx.Response) -> float | None:
    header = response.headers.get("retry-after")
    if header is None:
        return None
    try:
        return float(header)
    except ValueError:
        return None
