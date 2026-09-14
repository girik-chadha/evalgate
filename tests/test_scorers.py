import anyio
import pytest

from evalgate.models import (
    Assertion,
    ContainsAssertion,
    JudgeAssertion,
    NotContainsAssertion,
    RegexAssertion,
    Score,
)
from evalgate.scorers.deterministic import DeterministicScorer

CONTAINS = ContainsAssertion(type="contains", value="30 days")
NOT_CONTAINS = NotContainsAssertion(type="not_contains", value="no refunds")
REGEX = RegexAssertion(type="regex", pattern="[0-9]+ days")


def score(output: str, assertion: Assertion) -> Score:
    return anyio.run(DeterministicScorer().score, "the question", output, assertion)


@pytest.mark.parametrize(
    ("assertion", "output", "passed"),
    [
        (CONTAINS, "You have 30 days.", True),
        (CONTAINS, "You have a month.", False),
        (NOT_CONTAINS, "Refunds within 30 days.", True),
        (NOT_CONTAINS, "Sorry, no refunds.", False),
        (REGEX, "Returns accepted for 30 days.", True),
        (REGEX, "Returns accepted for thirty days.", False),
    ],
)
def test_deterministic_assertions(
    assertion: Assertion, output: str, passed: bool
) -> None:
    result = score(output, assertion)
    assert result.passed is passed
    assert result.value == (1.0 if passed else 0.0)
    assert result.assertion == assertion
    assert result.detail


def test_contains_is_case_sensitive() -> None:
    assert score("You have 30 Days.", CONTAINS).passed is False


def test_judge_is_refused() -> None:
    judge = JudgeAssertion(type="judge", criterion="helpful", min_score=0.5)
    with pytest.raises(TypeError, match="judge"):
        score("anything", judge)
