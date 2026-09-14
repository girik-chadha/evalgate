import hashlib
import json
import sqlite3
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Self

from evalgate.providers.base import Provider

SCHEMA = """
CREATE TABLE IF NOT EXISTS completions (
    key TEXT PRIMARY KEY,
    model TEXT NOT NULL,
    prompt TEXT NOT NULL,
    output TEXT NOT NULL,
    created_at TEXT NOT NULL
)
"""


def cache_key(model: str, prompt: str, params: Mapping[str, Any]) -> str:
    payload = json.dumps(
        {"model": model, "prompt": prompt, "params": params}, sort_keys=True
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class Cache:
    """Content-addressed store of completions in one sqlite file.

    Every write is committed on its own, so a run that dies part-way keeps
    every reply it already paid for.
    """

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path, autocommit=True)
        self._db.execute(SCHEMA)
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> str | None:
        row = self._db.execute(
            "SELECT output FROM completions WHERE key = ?", (key,)
        ).fetchone()
        if row is None:
            self.misses += 1
            return None
        self.hits += 1
        return row[0]

    def put(self, key: str, *, model: str, prompt: str, output: str) -> None:
        self._db.execute(
            "INSERT OR REPLACE INTO completions VALUES (?, ?, ?, ?, ?)",
            (key, model, prompt, output, datetime.now(UTC).isoformat()),
        )

    def close(self) -> None:
        self._db.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


class CachingProvider:
    """Serves a reply from the cache when the same model, prompt and params
    were seen before; otherwise calls the inner provider and stores the reply."""

    def __init__(self, inner: Provider, cache: Cache) -> None:
        self._inner = inner
        self._cache = cache

    @property
    def model(self) -> str:
        return self._inner.model

    @property
    def params(self) -> Mapping[str, Any]:
        return self._inner.params

    async def complete(
        self, prompt: str, *, response_schema: dict[str, Any] | None = None
    ) -> str:
        params = {**self._inner.params, "response_schema": response_schema}
        key = cache_key(self.model, prompt, params)
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        output = await self._inner.complete(prompt, response_schema=response_schema)
        self._cache.put(key, model=self.model, prompt=prompt, output=output)
        return output
