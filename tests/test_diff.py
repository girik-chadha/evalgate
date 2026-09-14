from datetime import UTC, datetime

import pytest

from evalgate.diff import Policy, compare
from evalgate.models import CaseResult, ContainsAssertion, RunReport, Score

ASSERTION = ContainsAssertion(type="contains", value="x")
NOW = datetime(2026, 9, 14, tzinfo=UTC)


def report(model: str = "m", **cases: tuple[bool, float]) -> RunReport:
    results = [
        CaseResult(
            case_id=case_id,
            output="reply",
            scores=[
                Score(
                    assertion=ASSERTION,
                    passed=passed,
                    value=value,
                    detail="" if passed else "'x' not found",
                )
            ],
            latency_ms=1.0,
        )
        for case_id, (passed, value) in cases.items()
    ]
    return RunReport(
        suite="s", model=model, started_at=NOW, duration_ms=1.0, results=results
    )


def test_every_status_is_assigned() -> None:
    base = report(a=(True, 1.0), b=(False, 0.5), c=(True, 1.0), d=(True, 1.0))
    current = report(a=(False, 0.0), b=(True, 1.0), c=(True, 1.0), e=(True, 1.0))
    diff = compare(base, current)
    assert {c.case_id: c.status for c in diff.cases} == {
        "a": "regressed",
        "b": "improved",
        "c": "unchanged",
        "e": "new",
        "d": "removed",
    }
    assert [c.case_id for c in diff.cases] == ["a", "b", "c", "e", "d"]
    assert diff.new_failures == ["a"]
    assert diff.regressed
    assert "1 new failure(s), max 0: a" in diff.violations[0]


def test_new_failing_case_counts_as_a_new_failure() -> None:
    diff = compare(report(a=(True, 1.0)), report(a=(True, 1.0), b=(False, 0.0)))
    assert diff.new_failures == ["b"]
    assert diff.regressed


def test_failure_already_in_the_baseline_is_accepted() -> None:
    diff = compare(report(a=(False, 0.2)), report(a=(False, 0.2)))
    assert diff.new_failures == []
    assert diff.cases[0].status == "unchanged"
    assert diff.regressed is False


def test_policy_can_tolerate_new_failures() -> None:
    base = report(a=(True, 1.0), b=(True, 1.0))
    current = report(a=(False, 0.0), b=(True, 1.0))
    lenient = Policy(max_new_failures=1, max_score_drop=1.0)
    strict = Policy(max_new_failures=0, max_score_drop=1.0)
    assert compare(base, current, lenient).regressed is False
    assert compare(base, current, strict).regressed is True


def test_the_two_levers_are_independent() -> None:
    base = report(a=(True, 1.0), b=(True, 1.0))
    current = report(a=(False, 0.0), b=(True, 1.0))
    diff = compare(base, current, Policy(max_new_failures=1))
    assert diff.new_failures == ["a"]
    assert diff.regressed
    assert len(diff.violations) == 1
    assert "fell 0.50" in diff.violations[0]


def test_score_drop_is_measured_over_shared_cases_only() -> None:
    base = report(a=(True, 1.0), b=(True, 1.0))
    current = report(a=(True, 0.8), b=(True, 0.8), c=(True, 0.0))
    diff = compare(base, current)
    assert diff.new_failures == []
    assert diff.shared == 2
    assert diff.baseline_mean == pytest.approx(1.0)
    assert diff.current_mean == pytest.approx(0.8)
    assert diff.regressed
    assert "fell 0.20" in diff.violations[0]


def test_drop_exactly_at_the_limit_is_not_a_regression() -> None:
    assert compare(report(a=(True, 0.90)), report(a=(True, 0.85))).regressed is False
    assert compare(report(a=(True, 0.90)), report(a=(True, 0.84))).regressed is True


def test_improvement_is_never_a_drop() -> None:
    diff = compare(report(a=(True, 0.5)), report(a=(True, 1.0)))
    assert diff.score_drop == 0.0
    assert diff.cases[0].delta == pytest.approx(0.5)


def test_no_shared_cases_means_no_score_comparison() -> None:
    diff = compare(report(a=(True, 1.0)), report(b=(True, 1.0)))
    assert diff.baseline_mean is None
    assert diff.current_mean is None
    assert diff.shared == 0
    assert diff.regressed is False


def test_models_are_recorded_for_the_reader() -> None:
    diff = compare(
        report("fake", a=(True, 1.0)), report("claude-sonnet-5", a=(True, 1.0))
    )
    assert (diff.baseline_model, diff.current_model) == ("fake", "claude-sonnet-5")


def test_detail_comes_from_the_current_run() -> None:
    diff = compare(report(a=(True, 1.0)), report(a=(False, 0.0)))
    assert diff.cases[0].detail == "'x' not found"
