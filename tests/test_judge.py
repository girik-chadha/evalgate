from typing import Any

import anyio
import pytest

from evalgate.models import Assertion, ContainsAssertion, JudgeAssertion, Score
from evalgate.scorers.judge import JUDGE_SCHEMA, JudgeScorer

ASSERTION = JudgeAssertion(
    type="judge", criterion="States the refund window", min_score=0.7
)


class SequenceProvider:
    model = "sequence"
    params: dict[str, Any] = {}

    def __init__(self, replies: list[str]) -> None:
        self._replies = list(replies)
        self.prompts: list[str] = []
        self.schemas: list[dict[str, Any] | None] = []

    async def complete(
        self, prompt: str, *, response_schema: dict[str, Any] | None = None
    ) -> str:
        self.prompts.append(prompt)
        self.schemas.append(response_schema)
        return self._replies.pop(0)


def verdict(score: float, reason: str = "fine") -> str:
    return f'{{"score": {score}, "reason": "{reason}"}}'


def score(
    provider: SequenceProvider, votes: int = 3, assertion: Assertion = ASSERTION
) -> Score:
    scorer = JudgeScorer(provider, votes=votes)
    return anyio.run(
        scorer.score, "How long do I have to return it?", "You have 30 days.", assertion
    )


def test_mean_of_votes_decides_the_pass() -> None:
    provider = SequenceProvider(
        [verdict(0.9), verdict(0.8), verdict(0.7, "no next step offered")]
    )
    result = score(provider)
    assert result.passed is True
    assert result.value == pytest.approx(0.8)
    assert result.assertion == ASSERTION
    assert "no next step offered" in result.detail
    assert len(provider.prompts) == 3


def test_mean_below_the_minimum_fails() -> None:
    provider = SequenceProvider([verdict(0.6), verdict(0.5), verdict(0.9)])
    result = score(provider)
    assert result.passed is False
    assert result.value == pytest.approx(2 / 3)


def test_prompt_carries_criterion_input_output_and_schema() -> None:
    provider = SequenceProvider([verdict(1.0)])
    score(provider, votes=1)
    (prompt,) = provider.prompts
    assert "States the refund window" in prompt
    assert "How long do I have to return it?" in prompt
    assert "You have 30 days." in prompt
    assert "vote 1 of 1" in prompt
    assert provider.schemas == [JUDGE_SCHEMA]


def test_each_vote_gets_a_distinct_prompt() -> None:
    provider = SequenceProvider([verdict(1.0)] * 3)
    score(provider)
    assert len(set(provider.prompts)) == 3
    assert "vote 2 of 3" in provider.prompts[1]


def test_fenced_json_is_still_parsed() -> None:
    provider = SequenceProvider(['```json\n{"score": 0.9, "reason": "ok"}\n```'])
    assert score(provider, votes=1).value == 0.9


def test_invalid_votes_are_dropped_from_the_mean() -> None:
    provider = SequenceProvider(["not json", verdict(1.5), verdict(0.8)])
    result = score(provider)
    assert result.passed is True
    assert result.value == 0.8
    assert "1/3 votes" in result.detail


def test_no_valid_votes_fails_the_assertion() -> None:
    provider = SequenceProvider(["nope", "", "{}"])
    result = score(provider)
    assert result.passed is False
    assert result.value == 0.0
    assert "none of 3 votes" in result.detail


def test_refuses_other_assertion_types() -> None:
    with pytest.raises(TypeError, match="contains"):
        score(
            SequenceProvider([]),
            assertion=ContainsAssertion(type="contains", value="x"),
        )
