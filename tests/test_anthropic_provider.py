import json
from collections.abc import Callable

import anyio
import httpx
import pytest

from evalgate.providers.anthropic import API_URL, AnthropicProvider
from evalgate.providers.base import ProviderError

Handler = Callable[[httpx.Request], httpx.Response]


def make_provider(handler: Handler, **options: object) -> AnthropicProvider:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return AnthropicProvider("claude-sonnet-5", "sk-ant-test", client, **options)


def complete(provider: AnthropicProvider, prompt: str = "hi", **kwargs: object) -> str:
    return anyio.run(lambda: provider.complete(prompt, **kwargs))


def message_response(*texts: str) -> httpx.Response:
    content: list[dict[str, str]] = [{"type": "thinking", "thinking": ""}]
    content += [{"type": "text", "text": t} for t in texts]
    return httpx.Response(200, json={"content": content, "stop_reason": "end_turn"})


def test_sends_a_single_user_message_with_auth_headers() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return message_response("You have 30 days.")

    assert complete(make_provider(handler), "How long?") == "You have 30 days."
    (request,) = seen
    assert str(request.url) == API_URL
    assert request.headers["x-api-key"] == "sk-ant-test"
    assert request.headers["anthropic-version"] == "2023-06-01"
    assert json.loads(request.content) == {
        "model": "claude-sonnet-5",
        "max_tokens": 16000,
        "messages": [{"role": "user", "content": "How long?"}],
    }


def test_temperature_is_only_sent_when_set() -> None:
    bodies: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return message_response("ok")

    complete(make_provider(handler, temperature=0.0))
    assert bodies[0]["temperature"] == 0.0


def test_response_schema_becomes_output_config() -> None:
    bodies: list[dict[str, object]] = []
    schema = {"type": "object", "properties": {}, "additionalProperties": False}

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return message_response("{}")

    complete(make_provider(handler), response_schema=schema)
    assert bodies[0]["output_config"] == {
        "format": {"type": "json_schema", "schema": schema}
    }


def test_text_blocks_are_joined_and_other_blocks_ignored() -> None:
    provider = make_provider(lambda _: message_response("Part one. ", "Part two."))
    assert complete(provider) == "Part one. Part two."


@pytest.mark.parametrize("status", [429, 500, 529])
def test_rate_limits_and_server_errors_are_retryable(status: int) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status,
            json={"error": {"type": "overloaded_error", "message": "busy"}},
            headers={"retry-after": "7"},
        )

    with pytest.raises(ProviderError) as info:
        complete(make_provider(handler))
    assert info.value.retryable is True
    assert info.value.retry_after_s == 7.0
    assert f"HTTP {status} overloaded_error: busy" in str(info.value)


@pytest.mark.parametrize("status", [400, 401, 403, 404])
def test_client_errors_are_not_retryable(status: int) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status, json={"error": {"type": "invalid_request_error", "message": "no"}}
        )

    with pytest.raises(ProviderError) as info:
        complete(make_provider(handler))
    assert info.value.retryable is False
    assert info.value.retry_after_s is None


def test_non_json_error_body_is_still_reported() -> None:
    provider = make_provider(lambda _: httpx.Response(502, text="Bad Gateway"))
    with pytest.raises(ProviderError, match="HTTP 502 Bad Gateway"):
        complete(provider)


def test_timeouts_are_retryable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("too slow", request=request)

    with pytest.raises(ProviderError, match="ReadTimeout") as info:
        complete(make_provider(handler))
    assert info.value.retryable is True
