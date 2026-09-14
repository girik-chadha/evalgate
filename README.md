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

Prints one row per case and exits 0 when every case passed, 1 when any case
failed, 2 when the suite could not be loaded or the run could not start.

Useful options:

    --provider fake          answer from a canned replies file, no network
    --responses PATH         replies file for the fake; default <suite>.responses.yaml
    --judge-model MODEL      model that scores judge assertions; default claude-sonnet-5
    --judge-votes N          judge calls per assertion, averaged; default 3
    --concurrency N          provider calls in flight at once; default 4
    --retries N              retries per call on rate limits and server errors; default 2

The fake provider picks the reply whose key is the longest substring of the
prompt, so a replies file can answer both completion prompts (key on the
customer's question) and judge prompts (key on the criterion text). The whole
test suite and the `--provider fake` path run with zero network calls.

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
deterministic scorers, LLM judge with structured output and n-vote, async
runner with a concurrency limit, `run` command with a console table.

Not yet: response cache, baselines and regression diff, GitHub Actions
workflows, demo app.
