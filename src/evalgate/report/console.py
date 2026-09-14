from rich.console import Console
from rich.table import Table
from rich.text import Text

from evalgate.models import RunReport


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
        detail = result.error or "; ".join(
            s.detail for s in result.scores if not s.passed
        )
        table.add_row(
            Text(result.case_id),
            status,
            f"{result.score:.2f}",
            f"{result.latency_ms:.0f} ms",
            Text(detail),
        )
    console.print(table)
    total = len(report.results)
    failed = sum(not r.passed for r in report.results)
    console.print(
        f"{total} cases, {total - failed} passed, {failed} failed, "
        f"mean score {report.mean_score:.2f}, {report.duration_ms:.0f} ms",
        highlight=False,
    )
