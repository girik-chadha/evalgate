import re
from datetime import datetime
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ContainsAssertion(StrictModel):
    type: Literal["contains"]
    value: str = Field(min_length=1)


class NotContainsAssertion(StrictModel):
    type: Literal["not_contains"]
    value: str = Field(min_length=1)


class RegexAssertion(StrictModel):
    type: Literal["regex"]
    pattern: re.Pattern[str]


class JudgeAssertion(StrictModel):
    type: Literal["judge"]
    criterion: str = Field(min_length=1)
    min_score: float = Field(ge=0.0, le=1.0)


Assertion = Annotated[
    ContainsAssertion | NotContainsAssertion | RegexAssertion | JudgeAssertion,
    Field(discriminator="type"),
]


class TestCase(StrictModel):
    # pytest collects anything named Test*; this stops it trying.
    __test__ = False

    id: str = Field(min_length=1)
    prompt_template: str
    input: str
    assertions: list[Assertion] = Field(min_length=1)


class Suite(StrictModel):
    model_config = ConfigDict(validate_by_name=True)

    name: str = Field(alias="suite")
    model: str
    cases: list[TestCase] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_case_ids(self) -> Self:
        seen: set[str] = set()
        for case in self.cases:
            if case.id in seen:
                raise ValueError(f"duplicate case id: {case.id}")
            seen.add(case.id)
        return self


class Score(StrictModel):
    """One assertion's verdict. `passed` is the thresholded decision,
    `value` is the raw measurement in [0, 1] that produced it."""

    assertion: Assertion
    passed: bool
    value: float = Field(ge=0.0, le=1.0)
    detail: str = ""


class CaseResult(StrictModel):
    """`error` is set when the provider failed after retries; then
    `output` is None, `scores` is empty and the case counts as failed."""

    case_id: str
    output: str | None
    scores: list[Score]
    latency_ms: float
    error: str | None = None

    @property
    def passed(self) -> bool:
        return self.error is None and all(s.passed for s in self.scores)

    @property
    def score(self) -> float:
        if not self.scores:
            return 0.0
        return sum(s.value for s in self.scores) / len(self.scores)


class RunReport(StrictModel):
    suite: str
    model: str
    started_at: datetime
    duration_ms: float
    results: list[CaseResult] = Field(min_length=1)

    @property
    def passed(self) -> bool:
        return all(r.passed for r in self.results)

    @property
    def pass_rate(self) -> float:
        return sum(r.passed for r in self.results) / len(self.results)

    @property
    def mean_score(self) -> float:
        return sum(r.score for r in self.results) / len(self.results)
