from collections.abc import Mapping
from functools import partial
from pathlib import Path
from typing import Annotated, NoReturn

import anyio
import httpx
import typer
from rich.console import Console

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
HTTP_TIMEOUT_S = 120.0

app = typer.Typer(no_args_is_help=True, add_completion=False)
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
) -> None:
    """Run a suite and print one row per case. Exits 1 if any case failed."""
    if responses is None:
        responses = suite_path.with_name(f"{suite_path.stem}.responses.yaml")
    try:
        suite = load_suite(suite_path)
        templates = load_templates(suite, suite_path.parent)
        report = anyio.run(
            partial(
                _execute,
                suite,
                templates,
                provider_name=provider,
                responses=responses,
                judge_model=judge_model,
                judge_votes=judge_votes,
                concurrency=concurrency,
                retries=retries,
            )
        )
    except SuiteError as e:
        _fail(str(e))
    print_report(report)
    raise typer.Exit(0 if report.passed else 1)


async def _execute(
    suite: Suite,
    templates: Mapping[str, str],
    *,
    provider_name: str,
    responses: Path,
    judge_model: str,
    judge_votes: int,
    concurrency: int,
    retries: int,
) -> RunReport:
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_S) as client:
        completion, judge = _build_providers(
            provider_name, suite.model, judge_model, responses, client
        )
        deterministic = DeterministicScorer()
        scorers: dict[str, Scorer] = {
            "contains": deterministic,
            "not_contains": deterministic,
            "regex": deterministic,
            "judge": JudgeScorer(
                RetryingProvider(judge, retries=retries), votes=judge_votes
            ),
        }
        return await run_suite(
            suite,
            templates,
            RetryingProvider(completion, retries=retries),
            scorers,
            concurrency=concurrency,
        )


def _build_providers(
    name: str,
    model: str,
    judge_model: str,
    responses: Path,
    client: httpx.AsyncClient,
) -> tuple[Provider, Provider]:
    if name == "fake":
        if not responses.is_file():
            raise typer.BadParameter(f"{responses} not found", param_hint="--responses")
        fake = FakeProvider.from_file(responses)
        return fake, fake
    if name == "anthropic":
        key = Settings().anthropic_api_key
        if key is None or not key.get_secret_value():
            _fail("ANTHROPIC_API_KEY is not set; export it or put it in a .env file")
        secret = key.get_secret_value()
        return (
            AnthropicProvider(model, secret, client),
            AnthropicProvider(judge_model, secret, client),
        )
    raise typer.BadParameter(
        f"unknown provider {name!r}; use anthropic or fake", param_hint="--provider"
    )


def _fail(message: str) -> NoReturn:
    # Error text can contain [brackets]; rich must not read them as markup.
    stderr.print(message, markup=False, highlight=False)
    raise typer.Exit(2)
