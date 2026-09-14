from evalgate.models import (
    Assertion,
    ContainsAssertion,
    NotContainsAssertion,
    RegexAssertion,
    Score,
)


class DeterministicScorer:
    async def score(self, input: str, output: str, assertion: Assertion) -> Score:
        match assertion:
            case ContainsAssertion(value=value):
                passed = value in output
                detail = f"found {value!r}" if passed else f"{value!r} not found"
            case NotContainsAssertion(value=value):
                passed = value not in output
                detail = f"{value!r} absent" if passed else f"found forbidden {value!r}"
            case RegexAssertion(pattern=pattern):
                passed = pattern.search(output) is not None
                detail = (
                    f"matched {pattern.pattern!r}"
                    if passed
                    else f"no match for {pattern.pattern!r}"
                )
            case _:
                raise TypeError(f"deterministic scorer cannot score {assertion.type!r}")
        return Score(
            assertion=assertion,
            passed=passed,
            value=1.0 if passed else 0.0,
            detail=detail,
        )
