from rich.console import Console
from rich.table import Table
from rich.text import Text

from evalgate.diff import CaseDiff, Diff
from evalgate.models import RunReport

STATUS_STYLE = {
    "regressed": "red",
    "improved": "green",
    "new": "yellow",
    "removed": "yellow",
    "unchanged": "dim",
}


def print_report(report: RunReport, console: Console | None = None) -> None:
    console = console or Console()
    table = Table(title=Text(f"{report.suite} on {report.model}"))
    table.add_column("case", no_wrap=True)
    table.add_column("status")
    table.add_column("score", justify="right")
    table.add_column("latency", justify="right")
    table.add_column("detail")
    for result in report.results:
        if result.passed:
            status = Text("PASS", style="green")
        else:
            status = Text("FAIL", style="red")
        table.add_row(
            Text(result.case_id),
            status,
            f"{result.score:.2f}",
            f"{result.latency_ms:.0f} ms",
            Text(result.failure_detail),
        )
    console.print(table)
    total = len(report.results)
    failed = sum(not r.passed for r in report.results)
    console.print(
        f"{total} cases, {total - failed} passed, {failed} failed, "
        f"mean score {report.mean_score:.2f}, {report.duration_ms:.0f} ms",
        highlight=False,
    )


def print_diff(diff: Diff, console: Console | None = None) -> None:
    console = console or Console()
    table = Table(title=Text("against baseline"))
    table.add_column("case", no_wrap=True)
    table.add_column("baseline")
    table.add_column("current")
    table.add_column("delta", justify="right")
    table.add_column("status")
    table.add_column("detail")
    for case in diff.cases:
        table.add_row(
            Text(case.case_id),
            _outcome(case.baseline_passed, case.baseline_score),
            _outcome(case.current_passed, case.current_score),
            _delta(case),
            Text(case.status, style=STATUS_STYLE[case.status]),
            Text(case.detail),
        )
    console.print(table)
    if diff.baseline_model != diff.current_model:
        console.print(
            f"note: baseline ran on {diff.baseline_model}, "
            f"this run on {diff.current_model}",
            highlight=False,
        )
    if diff.regressed:
        for violation in diff.violations:
            console.print(Text(f"regression: {violation}", style="red"))
        return
    if diff.baseline_mean is None or diff.current_mean is None:
        summary = "no shared cases with the baseline"
    else:
        summary = (
            f"mean score {diff.baseline_mean:.2f} to {diff.current_mean:.2f} "
            f"over {diff.shared} shared cases, {len(diff.new_failures)} new failures"
        )
    console.print(Text(f"no regression against baseline: {summary}", style="green"))


def _outcome(passed: bool | None, score: float | None) -> str:
    if passed is None or score is None:
        return "-"
    return f"{'PASS' if passed else 'FAIL'} {score:.2f}"


def _delta(case: CaseDiff) -> str:
    if case.delta is None:
        return ""
    return f"{case.delta:+.2f}"
