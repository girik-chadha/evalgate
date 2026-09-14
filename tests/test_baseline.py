from datetime import UTC, datetime
from pathlib import Path

import pytest

from evalgate.baseline import (
    BaselineError,
    baseline_path,
    last_run_path,
    load_report,
    save_report,
)
from evalgate.errors import EvalgateError
from evalgate.loader import SuiteError
from evalgate.models import (
    CaseResult,
    JudgeAssertion,
    RegexAssertion,
    RunReport,
    Score,
)

REPORT = RunReport(
    suite="support_bot",
    model="fake",
    started_at=datetime(2026, 9, 14, 12, 0, tzinfo=UTC),
    duration_ms=12.5,
    results=[
        CaseResult(
            case_id="refund",
            output="You have 30 days.",
            scores=[
                Score(
                    assertion=RegexAssertion(type="regex", pattern="[0-9]+ days"),
                    passed=True,
                    value=1.0,
                ),
                Score(
                    assertion=JudgeAssertion(
                        type="judge", criterion="helpful", min_score=0.7
                    ),
                    passed=False,
                    value=0.6,
                    detail="judge 0.60",
                ),
            ],
            latency_ms=3.0,
        ),
        CaseResult(case_id="broken", output=None, scores=[], latency_ms=1.0, error="x"),
    ],
)


def test_report_round_trips_through_disk(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "support_bot.baseline.json"
    save_report(REPORT, path)
    assert load_report(path) == REPORT


def test_missing_report_is_a_baseline_error(tmp_path: Path) -> None:
    with pytest.raises(BaselineError, match="no report"):
        load_report(tmp_path / "missing.json")


def test_corrupt_report_is_a_baseline_error(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(BaselineError, match="not a valid report"):
        load_report(path)


def test_paths_sit_beside_the_suite_and_under_the_runs_dir() -> None:
    suite = Path("suites") / "support_bot.yaml"
    assert baseline_path(suite) == Path("suites") / "support_bot.baseline.json"
    runs = Path(".evalgate") / "runs"
    assert last_run_path(runs, "support_bot") == runs / "support_bot.json"


def test_user_facing_errors_share_a_base() -> None:
    assert issubclass(BaselineError, EvalgateError)
    assert issubclass(SuiteError, EvalgateError)
