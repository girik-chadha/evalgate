# Decisions

## src layout instead of a flat package

Package lives in src/evalgate and is used via `pip install -e .`.
Alternative: evalgate/ at the repo root, importable straight from the working directory.
Chosen because a flat layout lets tests pass against the working-directory copy while the
installed package is broken (file missing from the wheel, bad entry point). src forces every
import through the installed package, so packaging mistakes fail in CI, not on a user's machine.

## Assertions are a discriminated union, not one class with optional fields

Each assertion type is its own model, tagged by `type`.
Alternative: one Assertion class with value, criterion and min_score all optional.
Chosen because a typo, a missing field or an unknown type fails at load time with a precise
error, and each scorer receives exactly the fields it needs instead of checking for None.

## Models forbid unknown keys and are frozen

Alternative: pydantic's default, which silently ignores extra keys and allows mutation.
Chosen because the suite YAML is the public API. A misspelt key like `vlaue` would otherwise
be dropped, the field would take a default, and the assertion would pass for the wrong reason.
Frozen means a result cannot be edited after the runner produces it.

## Score stores both passed and value

Alternative: a single bool per assertion.
Chosen because `passed` is the thresholded decision and `value` is the raw measurement.
Keeping both means a stored baseline can be re-thresholded without re-running the model, and
regression becomes a numeric comparison rather than a count of booleans.

## A provider error is a failed case with score 0, not a skipped case

Alternative: leave errored cases out of the pass rate and mean score.
Chosen because retries live in the runner, so an error that reaches a result is real.
Excluding it would let a flaky provider make a run look better than the previous one.

## Prompt templates are text files beside the suite, with one `{{input}}` placeholder

Alternative: templates inline in the suite YAML, or a template engine such as Jinja.
Chosen because the prompt is the thing under test: a prompt edit must be a file diff in a PR
so that CI has an event to react to. One placeholder needs no engine and no escaping rules,
so `str.replace` is enough until a real case needs more.

## Providers raise ProviderError and mark whether it is worth retrying

Alternative: retry on any exception, or retry every ProviderError.
Chosen because retrying a bug in our own code would disguise it as flakiness and cost several
paid calls before it surfaced, and retrying a bad API key costs three attempts to learn one
fact. Only the provider can tell a rate limit from a programming error or a bad key, so it
raises ProviderError with `retryable` set; nothing above it looks at HTTP status codes.

## Scorers are async even when they do no I/O

Alternative: sync deterministic scorers, an async judge scorer, and a runner that checks which
kind it holds.
Chosen because the judge scorer has to be async (it calls a model), and one signature means the
runner has a single code path. Awaiting a coroutine that never suspends costs nothing measurable.

## The runner checks every assertion type has a scorer before making any call

Alternative: look scorers up lazily and fail on the first assertion nobody can score.
Chosen because with a real provider the lazy version pays for every case before the failure
and then throws the whole run away. Anything that can be validated up front is validated
before the first paid call.

## A report records the provider's model, not the suite's

Alternative: copy `model` from the suite file into the report.
Chosen because a report is evidence of what actually ran. The suite may say claude-sonnet-4-5
while the run used the fake provider; a baseline produced that way must never be mistaken for
a real one.

## The Anthropic provider speaks HTTP directly instead of using the SDK

Alternative: the official `anthropic` package.
Chosen because the SDK retries 429s and 5xx itself, which would sit underneath our own retry
layer and double every wait, and because the request is one POST with four fields. Owning the
call means owning the error classification, which is the part this tool is about. The cost is
tracking API changes by hand.

## Retry is a provider wrapper, not runner logic

Alternative: a retry loop inside the runner around the completion call.
Chosen because the judge scorer also calls a provider and needs the same retries. Wrapping once
at composition time gives every provider call in the process the same policy, and the runner
shrinks to orchestration. The fake provider stays retry-free so tests can count calls exactly.

## Scorers receive the user's input as well as the model's output

Alternative: `score(output, assertion)`, which is all the deterministic scorers needed.
Chosen because a judge cannot tell whether a reply "offers a next step" without seeing the
question. The signature was widened when the second implementation arrived rather than
guessed up front; the deterministic scorers simply ignore the extra argument.
