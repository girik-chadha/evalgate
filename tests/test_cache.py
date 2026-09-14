from pathlib import Path

import anyio

from evalgate.cache import Cache, CachingProvider, cache_key
from evalgate.providers.fake import FakeProvider

PARAMS = {"max_tokens": 100, "temperature": None}


def test_key_is_stable_for_equal_inputs() -> None:
    first = cache_key("m", "hello", {"a": 1, "b": {"c": 2}})
    second = cache_key("m", "hello", {"b": {"c": 2}, "a": 1})
    assert first == second
    assert len(first) == 64


def test_key_changes_when_any_input_changes() -> None:
    base = cache_key("m", "hello", PARAMS)
    assert cache_key("other", "hello", PARAMS) != base
    assert cache_key("m", "hello!", PARAMS) != base
    assert cache_key("m", "hello", {**PARAMS, "max_tokens": 101}) != base


def test_store_round_trips_and_survives_reopen(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "cache.db"
    with Cache(path) as cache:
        assert cache.get("k") is None
        cache.put("k", model="m", prompt="p", output="reply")
        assert cache.get("k") == "reply"
        assert (cache.hits, cache.misses) == (1, 1)
    with Cache(path) as reopened:
        assert reopened.get("k") == "reply"


def test_empty_reply_is_a_hit_not_a_miss(tmp_path: Path) -> None:
    with Cache(tmp_path / "cache.db") as cache:
        cache.put("k", model="m", prompt="p", output="")
        assert cache.get("k") == ""
        assert cache.hits == 1


def complete(provider: CachingProvider, prompt: str, **kwargs: object) -> str:
    return anyio.run(lambda: provider.complete(prompt, **kwargs))


def test_second_identical_call_never_reaches_the_provider(tmp_path: Path) -> None:
    inner = FakeProvider({"hello": "world"})
    with Cache(tmp_path / "cache.db") as cache:
        provider = CachingProvider(inner, cache)
        assert complete(provider, "hello") == "world"
        assert complete(provider, "hello") == "world"
        assert inner.calls == ["hello"]
        assert (cache.hits, cache.misses) == (1, 1)
        assert provider.model == "fake"
        assert provider.params["default"] == ""
        assert len(provider.params["responses"]) == 64


def test_schema_is_part_of_the_key(tmp_path: Path) -> None:
    inner = FakeProvider({"hello": "world"})
    with Cache(tmp_path / "cache.db") as cache:
        provider = CachingProvider(inner, cache)
        complete(provider, "hello")
        complete(provider, "hello", response_schema={"type": "object"})
        assert len(inner.calls) == 2


def test_different_models_do_not_share_entries(tmp_path: Path) -> None:
    class NamedFake(FakeProvider):
        def __init__(self, model: str) -> None:
            super().__init__({"hello": model})
            self.model = model

    with Cache(tmp_path / "cache.db") as cache:
        first = CachingProvider(NamedFake("one"), cache)
        second = CachingProvider(NamedFake("two"), cache)
        assert complete(first, "hello") == "one"
        assert complete(second, "hello") == "two"


def test_reply_table_is_part_of_the_fake_key(tmp_path: Path) -> None:
    with Cache(tmp_path / "cache.db") as cache:
        one = CachingProvider(FakeProvider({"hello": "one"}), cache)
        two = CachingProvider(FakeProvider({"hello": "two"}), cache)
        assert complete(one, "hello") == "one"
        assert complete(two, "hello") == "two"
