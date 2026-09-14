from functools import partial

import anyio
import pytest

from evalgate.loader import SuiteError
from evalgate.models import (
    ContainsAssertion,
    JudgeAssertion,
    RegexAssertion,
    RunReport,
    Suite,
    TestCase,
)
from evalgate.providers.fake import FakeProvider
from evalgate.runner import run_suite
from evalgate.scorers.deterministic import DeterministicScorer

DETERMINISTIC = DeterministicScorer()
SCORERS = {
    "contains": DETERMINISTIC,
    "not_contains": DETERMINISTIC,
    "regex": DETERMINISTIC,
}
TEMPLATES = {"support": "Customer: {{input}}"}
REPLIES = {
    "return a jacket": "You have 30 days.",
    "order arrive": "Usually 5 working days.",
}
SUITE = Suite(
    name="s",
    model="claude-sonnet-4-5",
    cases=[
        TestCase(
            id="refund",
            prompt_template="support",
            input="Can I return a jacket?",
            assertions=[ContainsAssertion(type="contains", value="30 days")],
        ),
        TestCase(
            id="shipping",
            prompt_template="support",
            input="When will my order arrive?",
            assertions=[RegexAssertion(type="regex", pattern="[0-9]+ working days")],
        ),
    ],
)


def run(provider: FakeProvider, suite: Suite = SUITE, **options: int) -> RunReport:
    return anyio.run(
        partial(run_suite, suite, TEMPLATES, provider, SCORERS, backoff_s=0, **options)
    )


def test_every_case_runs_in_suite_order_with_rendered_prompt() -> None:
    provider = FakeProvider(REPLIES)
    report = run(provider)
    assert report.passed
    assert report.model == "fake"
    assert [r.case_id for r in report.results] == ["refund", "shipping"]
    assert report.results[0].output == "You have 30 days."
    assert sorted(provider.calls) == [
        "Customer: Can I return a jacket?",
        "Customer: When will my order arrive?",
    ]


def test_failed_assertion_fails_the_case_but_not_the_run() -> None:
    provider = FakeProvider({**REPLIES, "return a jacket": "Ask legal."})
    report = run(provider)
    refund, shipping = report.results
    assert refund.passed is False
    assert refund.scores[0].detail == "'30 days' not found"
    assert shipping.passed is True
    assert report.pass_rate == 0.5


def test_transient_errors_are_retried() -> None:
    provider = FakeProvider(REPLIES, fail_first=1)
    report = run(provider, retries=1)
    assert report.passed
    assert len(provider.calls) == 3


def test_exhausted_retries_record_an_error_instead_of_raising() -> None:
    provider = FakeProvider(REPLIES, fail_first=1)
    report = run(provider, retries=0)
    errored = [r for r in report.results if r.error]
    assert len(errored) == 1
    assert errored[0].output is None
    assert errored[0].scores == []
    assert errored[0].score == 0.0
    assert report.passed is False


def test_missing_scorer_fails_before_any_call() -> None:
    provider = FakeProvider(REPLIES)
    judged = Suite(
        name="j",
        model="m",
        cases=[
            TestCase(
                id="a",
                prompt_template="support",
                input="x",
                assertions=[
                    JudgeAssertion(type="judge", criterion="helpful", min_score=0.5)
                ],
            )
        ],
    )
    with pytest.raises(SuiteError, match="judge"):
        run(provider, suite=judged)
    assert provider.calls == []


class SlowProvider:
    model = "slow"

    def __init__(self) -> None:
        self.in_flight = 0
        self.max_in_flight = 0

    async def complete(self, prompt: str) -> str:
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        await anyio.sleep(0.01)
        self.in_flight -= 1
        return "You have 30 days."


def test_concurrency_limit_is_respected() -> None:
    provider = SlowProvider()
    suite = Suite(
        name="s",
        model="m",
        cases=[
            TestCase(
                id=f"case_{i}",
                prompt_template="support",
                input="x",
                assertions=[ContainsAssertion(type="contains", value="30 days")],
            )
            for i in range(6)
        ],
    )
    anyio.run(partial(run_suite, suite, TEMPLATES, provider, SCORERS, concurrency=2))
    assert provider.max_in_flight == 2
