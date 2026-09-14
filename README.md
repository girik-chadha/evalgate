# evalgate

Prompt regression testing. Define test cases in YAML, run them against an LLM,
score the non-deterministic output, and fail CI when quality drops below a
stored baseline.

## Setup (Windows)

    python -m venv .venv
    .venv\Scripts\activate
    pip install -e ".[dev]"

Set `ANTHROPIC_API_KEY` in the environment or in a `.env` file at the repo
root (`.env` is gitignored).

## Run a suite

    evalgate run suites\support_bot.yaml

Prints one row per case. Without a baseline it exits 0 when every case passed
and 1 otherwise. With a baseline it exits 1 on a regression (see below) and 0
otherwise, even if the baseline already had failing cases. Exit 2 means the
suite could not be loaded or the run could not start.

Useful options:

    --provider fake          answer from a canned replies file, no network
    --responses PATH         replies file for the fake; default <suite>.responses.yaml
    --judge-model MODEL      model that scores judge assertions; default claude-sonnet-5
    --judge-votes N          judge calls per assertion, averaged; default 3
    --concurrency N          provider calls in flight at once; default 4
    --retries N              retries per call on rate limits and server errors; default 2
    --cache PATH             sqlite file of cached replies; default .evalgate\cache.db
    --no-cache               call the provider even for prompts seen before
    --baseline PATH          report to compare against; default <suite>.baseline.json
    --max-new-failures N     new failures tolerated before a regression; default 0
    --max-score-drop X       mean score drop tolerated over shared cases; default 0.05

The fake provider picks the reply whose key is the longest substring of the
prompt, so a replies file can answer both completion prompts (key on the
customer's question) and judge prompts (key on the criterion text). The whole
test suite and the `--provider fake` path run with zero network calls.

## Baselines

    evalgate run suites\support_bot.yaml        # look at the table
    evalgate baseline suites\support_bot.yaml   # accept that run
    git add suites\support_bot.baseline.json

`run` records its report under `.evalgate\runs\`. `baseline` copies the last
recorded run to `<suite>.baseline.json`, which you commit: it is the accepted
state, including any failures you have decided to live with. `baseline`
refuses a run that had provider errors, since that is not a measurement.

Every later `run` compares against it and prints a second table with one row
per case: regressed, improved, unchanged, new, or removed. A run is a
regression when either lever trips:

- more new failures than `--max-new-failures`. A new failure is a failing case
  the baseline did not have failing, whether it passed there or did not exist.
- the mean score over cases present in both runs fell by more than
  `--max-score-drop`. Added and removed cases cannot move this number.

The baseline records which model produced it. When the current run used a
different model the diff says so, which is the expected situation when you
are testing a model swap.

## Cache

Every reply is stored in `.evalgate\cache.db` (gitignored), keyed on the
model, the exact prompt and the request settings. Re-running an unchanged
suite makes no provider calls and returns the same answers; editing a prompt
template misses for every case that uses it. Judge votes are cached one by
one. The run prints `cache: N hits, M misses` after the table. Use
`--no-cache` for fresh samples, and `--cache PATH` to put the file somewhere
a CI cache can keep it between runs.

## Suite format

```yaml
suite: support_bot
model: claude-sonnet-4-5
cases:
  - id: refund_window
    prompt_template: support_v2
    input: "How long do I have to return a jacket?"
    assertions:
      - type: contains
        value: "30 days"
      - type: not_contains
        value: "no refunds"
      - type: regex
        pattern: '[0-9]+ days'
      - type: judge
        criterion: "States the refund window and offers a next step"
        min_score: 0.7
```

`prompt_template` names a file at `prompts\<name>.txt` next to the suite. The
file must contain the placeholder `{{input}}`, which is replaced with the
case's `input` to form the prompt.

Assertion types:

- `contains` / `not_contains`: case-sensitive substring check.
- `regex`: `re.search` with the pattern, compiled at load time. Single-quote
  patterns in YAML; double quotes process backslash escapes, so `"\d+"` is a
  parse error while `'\d+'` is not.
- `judge`: asks the judge model to score the reply against `criterion` from 0
  to 1, several votes, and passes when the mean reaches `min_score`.

Unknown keys anywhere in the suite are rejected, so a typo fails at load time
rather than silently passing.

## Development

    pytest
    ruff check .
    ruff format .

## Status

Done: models, loader, Anthropic and fake providers, retries with backoff,
sqlite reply cache, deterministic scorers, LLM judge with structured output
and n-vote, async runner with a concurrency limit, `run` and `baseline`
commands, regression diff with a two-lever policy.

Not yet: markdown report for PR comments, GitHub Actions workflows, demo app.
