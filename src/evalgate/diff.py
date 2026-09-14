from typing import Literal

from pydantic import Field

from evalgate.models import CaseResult, RunReport, StrictModel

Status = Literal["regressed", "improved", "unchanged", "new", "removed"]

# Guards the comparison against float noise such as 0.9 - 0.85 > 0.05.
TOLERANCE = 1e-9


class Policy(StrictModel):
    """What counts as a regression.

    A new failure is a failing case the baseline did not already have failing,
    whether it passed there or did not exist. The score drop is measured over
    cases present in both runs, so added and removed cases cannot move it.
    """

    max_new_failures: int = Field(default=0, ge=0)
    max_score_drop: float = Field(default=0.05, ge=0.0)


class CaseDiff(StrictModel):
    case_id: str
    status: Status
    baseline_passed: bool | None = None
    baseline_score: float | None = None
    current_passed: bool | None = None
    current_score: float | None = None
    detail: str = ""

    @property
    def delta(self) -> float | None:
        if self.baseline_score is None or self.current_score is None:
            return None
        return self.current_score - self.baseline_score


class Diff(StrictModel):
    policy: Policy
    baseline_model: str
    current_model: str
    baseline_mean: float | None
    current_mean: float | None
    cases: list[CaseDiff]

    @property
    def shared(self) -> int:
        return sum(c.delta is not None for c in self.cases)

    @property
    def new_failures(self) -> list[str]:
        return [
            c.case_id
            for c in self.cases
            if c.current_passed is False and c.baseline_passed is not False
        ]

    @property
    def score_drop(self) -> float:
        if self.baseline_mean is None or self.current_mean is None:
            return 0.0
        return max(0.0, self.baseline_mean - self.current_mean)

    @property
    def violations(self) -> list[str]:
        found: list[str] = []
        failures = self.new_failures
        if len(failures) > self.policy.max_new_failures:
            found.append(
                f"{len(failures)} new failure(s), max {self.policy.max_new_failures}: "
                + ", ".join(failures)
            )
        if self.score_drop > self.policy.max_score_drop + TOLERANCE:
            found.append(
                f"mean score over {self.shared} shared cases fell "
                f"{self.score_drop:.2f}, from {self.baseline_mean:.2f} to "
                f"{self.current_mean:.2f}, max {self.policy.max_score_drop:.2f}"
            )
        return found

    @property
    def regressed(self) -> bool:
        return bool(self.violations)


def compare(
    baseline: RunReport, current: RunReport, policy: Policy | None = None
) -> Diff:
    before = {r.case_id: r for r in baseline.results}
    after = {r.case_id: r for r in current.results}
    cases = [_case_diff(before.get(r.case_id), r) for r in current.results]
    cases += [_case_diff(r, None) for r in baseline.results if r.case_id not in after]
    shared = [c for c in cases if c.delta is not None]
    return Diff(
        policy=policy or Policy(),
        baseline_model=baseline.model,
        current_model=current.model,
        baseline_mean=_mean([c.baseline_score for c in shared]),
        current_mean=_mean([c.current_score for c in shared]),
        cases=cases,
    )


def _case_diff(before: CaseResult | None, after: CaseResult | None) -> CaseDiff:
    if before is None:
        assert after is not None
        status: Status = "new"
    elif after is None:
        status = "removed"
    elif before.passed and not after.passed:
        status = "regressed"
    elif not before.passed and after.passed:
        status = "improved"
    else:
        status = "unchanged"
    return CaseDiff(
        case_id=(after or before).case_id,
        status=status,
        baseline_passed=None if before is None else before.passed,
        baseline_score=None if before is None else before.score,
        current_passed=None if after is None else after.passed,
        current_score=None if after is None else after.score,
        detail="" if after is None else after.failure_detail,
    )


def _mean(values: list[float | None]) -> float | None:
    present = [v for v in values if v is not None]
    if not present:
        return None
    return sum(present) / len(present)
