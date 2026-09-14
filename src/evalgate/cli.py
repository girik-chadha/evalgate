from functools import partial
from pathlib import Path
from typing import Annotated

import anyio
import typer
from rich.console import Console

from evalgate.loader import SuiteError, load_suite, load_templates
from evalgate.providers.base import Provider
from evalgate.providers.fake import FakeProvider
from evalgate.report.console import print_report
from evalgate.runner import run_suite
from evalgate.scorers.deterministic import DeterministicScorer

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
    provider: Annotated[str, typer.Option(help="only 'fake' exists so far")] = "fake",
    responses: Annotated[
        Path | None,
        typer.Option(help="fake provider replies; default <suite>.responses.yaml"),
    ] = None,
    concurrency: Annotated[int, typer.Option(min=1)] = 4,
    retries: Annotated[int, typer.Option(min=0)] = 2,
) -> None:
    """Run a suite and print one row per case. Exits 1 if any case failed."""
    deterministic = DeterministicScorer()
    scorers = {
        "contains": deterministic,
        "not_contains": deterministic,
        "regex": deterministic,
    }
    if responses is None:
        responses = suite_path.with_name(f"{suite_path.stem}.responses.yaml")
    try:
        suite = load_suite(suite_path)
        templates = load_templates(suite, suite_path.parent)
        chosen = _build_provider(provider, responses)
        report = anyio.run(
            partial(
                run_suite,
                suite,
                templates,
                chosen,
                scorers,
                concurrency=concurrency,
                retries=retries,
            )
        )
    except SuiteError as e:
        # Error text can contain [brackets]; rich must not read them as markup.
        stderr.print(str(e), markup=False, highlight=False)
        raise typer.Exit(2) from e
    print_report(report)
    raise typer.Exit(0 if report.passed else 1)


def _build_provider(name: str, responses: Path) -> Provider:
    if name != "fake":
        raise typer.BadParameter(
            f"unknown provider {name!r}; only 'fake' exists so far",
            param_hint="--provider",
        )
    if not responses.is_file():
        raise typer.BadParameter(f"{responses} not found", param_hint="--responses")
    return FakeProvider.from_file(responses)
