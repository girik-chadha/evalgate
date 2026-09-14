from typing import Any

from pydantic import BaseModel, Field, ValidationError

from evalgate.models import Assertion, JudgeAssertion, Score
from evalgate.providers.base import Provider

JUDGE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "score": {"type": "number"},
        "reason": {"type": "string"},
    },
    "required": ["score", "reason"],
    "additionalProperties": False,
}

PROMPT = """\
You are grading one reply from an AI assistant against a single criterion.

Criterion: {criterion}

The user asked:
<input>
{input}
</input>

The assistant replied:
<output>
{output}
</output>

Score how well the reply meets the criterion, from 0.0 (not at all) to 1.0 (fully).
Give partial credit only for partial compliance. Judge the reply as written; do not
reward length or politeness unless the criterion asks for them.
This is vote {vote} of {votes}; score independently of any other vote.
Respond with JSON only, in the form {{"score": <number>, "reason": "<one sentence>"}}.
"""


class Verdict(BaseModel):
    score: float = Field(ge=0.0, le=1.0)
    reason: str


class JudgeScorer:
    """LLM-as-judge.

    Asks `votes` times, drops replies that are not valid verdicts, and passes
    when the mean score reaches the assertion's `min_score`. No valid votes at
    all is a fail, not a pass: an unreadable judge is not evidence of quality.

    Each vote's prompt names its index so the votes stay distinct in the cache;
    otherwise vote two and three would be served from vote one.
    """

    def __init__(self, provider: Provider, *, votes: int = 3) -> None:
        self._provider = provider
        self._votes = votes

    async def score(self, input: str, output: str, assertion: Assertion) -> Score:
        if not isinstance(assertion, JudgeAssertion):
            raise TypeError(f"judge scorer cannot score {assertion.type!r}")
        verdicts: list[Verdict] = []
        for vote in range(1, self._votes + 1):
            prompt = PROMPT.format(
                criterion=assertion.criterion,
                input=input,
                output=output,
                vote=vote,
                votes=self._votes,
            )
            reply = await self._provider.complete(prompt, response_schema=JUDGE_SCHEMA)
            verdict = _parse(reply)
            if verdict is not None:
                verdicts.append(verdict)
        if not verdicts:
            return Score(
                assertion=assertion,
                passed=False,
                value=0.0,
                detail=f"judge: none of {self._votes} votes was a valid verdict",
            )
        mean = sum(v.score for v in verdicts) / len(verdicts)
        lowest = min(verdicts, key=lambda v: v.score)
        return Score(
            assertion=assertion,
            passed=mean >= assertion.min_score,
            value=mean,
            detail=(
                f"judge {mean:.2f} from {len(verdicts)}/{self._votes} votes, "
                f"min {assertion.min_score}: {lowest.reason}"
            ),
        )


def _parse(reply: str) -> Verdict | None:
    start, end = reply.find("{"), reply.rfind("}")
    if start == -1 or end == -1:
        return None
    try:
        return Verdict.model_validate_json(reply[start : end + 1])
    except ValidationError:
        return None
