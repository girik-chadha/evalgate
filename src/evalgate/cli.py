from collections.abc import Mapping
from functools import partial
from pathlib import Path
from typing import Annotated, NoReturn

import anyio
import httpx
import typer
from rich.console import Console

from evalgate.cache import Cache, CachingProvider
from evalgate.config import Settings
from evalgate.loader import SuiteError, load_suite, load_templates
from evalgate.models import RunReport, Suite
from evalgate.providers.anthropic import AnthropicProvider
from evalgate.providers.base import Provider
from evalgate.providers.fake import FakeProvider
from evalgate.providers.retry import RetryingProvider
from evalgate.report.console import print_report
from evalgate.runner import run_suite
from evalgate.scorers.base import Scorer
from evalgate.scorers.deterministic import DeterministicScorer
from evalgate.scorers.judge import JudgeScorer

DEFAULT_JUDGE_MODEL = "claude-sonnet-5"
DEFAULT_CACHE = Path(".evalgate/cache.db")
HTTP_TIMEOUT_S = 120.0

app = typer.Typer(no_args_is_help=True, add_completion=False)
stdout = Console()
stderr = Console(stderr=True)


@app.callback()
def main() -> None:
    """Prompt regression testing."""


@app.command()
def run(
    suite_path: Annotated[
        Path, typer.Argument(exists=True, dir_okay=False, help="suite YAML file")
    ],
    provider: Annotated[str, typer.Option(help="anthropic or fake")] = "anthropic",
    responses: Annotated[
        Path | None,
        typer.Option(help="fake provider replies; default <suite>.responses.yaml"),
    ] = None,
    judge_model: Annotated[
        str, typer.Option(help="model that scores judge assertions")
    ] = DEFAULT_JUDGE_MODEL,
    judge_votes: Annotated[
        int, typer.Option(min=1, help="judge calls per assertion")
    ] = 3,
    concurrency: Annotated[int, typer.Option(min=1)] = 4,
    retries: Annotated[int, typer.Option(min=0)] = 2,
    cache: Annotated[
        Path, typer.Option(help="sqlite file of cached replies")
    ] = DEFAULT_CACHE,
    no_cache: Annotated[
        bool,
        typer.Option(
            "--no-cache", help="call the provider even for prompts seen before"
        ),
    ] = False,
) -> None:
    """Run a suite and print one row per case. Exits 1 if any case failed."""
    if responses is None:
        responses = suite_path.with_name(f"{suite_path.stem}.responses.yaml")
    store: Cache | None = None
    try:
        suite = load_suite(suite_path)
        templates = load_templates(suite, suite_path.parent)
        api_key = _check_provider(provider, responses)
        store = None if no_cache else Cache(cache)
        report = anyio.run(
            partial(
                _execute,
                suite,
                templates,
                provider_name=provider,
                api_key=api_key,
                responses=responses,
                judge_model=judge_model,
                judge_votes=judge_votes,
                concurrency=concurrency,
                retries=retries,
                store=store,
            )
        )
    except SuiteError as e:
        _fail(str(e))
    finally:
        if store is not None:
            store.close()
    print_report(report)
    if store is not None:
        stdout.print(
            f"cache: {store.hits} hits, {store.misses} misses", highlight=False
        )
    raise typer.Exit(0 if report.passed else 1)


async def _execute(
    suite: Suite,
    templates: Mapping[str, str],
    *,
    provider_name: str,
    api_key: str | None,
    responses: Path,
    judge_model: str,
    judge_votes: int,
    concurrency: int,
    retries: int,
    store: Cache | None,
) -> RunReport:
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_S) as client:
        completion: Provider
        judge: Provider
        if provider_name == "fake":
            completion = judge = FakeProvider.from_file(responses)
        else:
            assert api_key is not None
            completion = AnthropicProvider(suite.model, api_key, client)
            judge = AnthropicProvider(judge_model, api_key, client)
        completion = RetryingProvider(completion, retries=retries)
        judge = RetryingProvider(judge, retries=retries)
        if store is not None:
            completion = CachingProvider(completion, store)
            judge = CachingProvider(judge, store)
        deterministic = DeterministicScorer()
        scorers: dict[str, Scorer] = {
            "contains": deterministic,
            "not_contains": deterministic,
            "regex": deterministic,
            "judge": JudgeScorer(judge, votes=judge_votes),
        }
        return await run_suite(
            suite, templates, completion, scorers, concurrency=concurrency
        )


def _check_provider(name: str, responses: Path) -> str | None:
    """Fail fast on anything the run would need before spending a call."""
    if name == "fake":
        if not responses.is_file():
            raise typer.BadParameter(f"{responses} not found", param_hint="--responses")
        return None
    if name == "anthropic":
        key = Settings().anthropic_api_key
        if key is None or not key.get_secret_value():
            _fail("ANTHROPIC_API_KEY is not set; export it or put it in a .env file")
        return key.get_secret_value()
    raise typer.BadParameter(
        f"unknown provider {name!r}; use anthropic or fake", param_hint="--provider"
    )


def _fail(message: str) -> NoReturn:
    # Error text can contain [brackets]; rich must not read them as markup.
    stderr.print(message, markup=False, highlight=False)
    raise typer.Exit(2)
