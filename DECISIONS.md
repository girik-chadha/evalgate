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

## The judge takes several votes and applies the threshold in code

Alternative: one judge call that returns pass or fail directly.
Chosen because a single sample hides how sure the judge is, and asking the model for a verdict
hands it the policy decision. Each vote is a structured 0 to 1 score; the mean is compared to
`min_score` in code, so the threshold is visible, versioned and re-tunable without re-running.
Votes that are not valid verdicts are dropped, and no valid votes is a fail, never a pass.

## The judge runs on its own model, sampled at the API default

Alternative: judge with the model under test at temperature 0.
Chosen because current models reject `temperature` with a 400, so determinism by knob is not
on offer, and sampling variety is what makes three votes informative rather than three copies.
A separate model stops a model grading its own style, and lets the judge stay pinned while the
model under test changes, which is the comparison the tool exists to make.

## The cache is a provider wrapper keyed on model, prompt and request params

Alternative: a cache inside the runner keyed on case id, or a TTL cache keyed on prompt alone.
Chosen because the case id is not what determines the reply; the prompt, the model and settings
such as max_tokens are. Content addressing means an edited prompt misses and an unchanged one
hits, with no invalidation logic to get wrong, and wrapping the provider means judge calls are
cached by the same code. There is no TTL: an unchanged suite re-runs for free and returns the
same answers, and `--no-cache` exists for when fresh samples are wanted.

## Every cache write commits immediately

Alternative: one transaction per run, committed at the end.
Chosen because a run killed at call 150 of 200 should keep 150 paid replies. A commit per write
costs milliseconds against network calls that cost hundreds.

## Judge votes carry their index in the prompt so the cache keeps them apart

Alternative: bypass the cache for judge calls, or add a hidden salt to the cache key.
Chosen because judge calls are most of the spend, so they must be cached, and three votes with
byte-identical prompts would collapse to one cached reply. Naming the vote in the prompt keeps
the key honest (the prompt really is different) and makes a cached re-run reproduce the same
verdict rather than a fresh sample.
