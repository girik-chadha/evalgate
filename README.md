# evalgate

Prompt regression testing. Define test cases in YAML, run them against an LLM,
score the non-deterministic output, and fail CI when quality drops below a
stored baseline.

## Setup (Windows)

    python -m venv .venv
    .venv\Scripts\activate
    pip install -e ".[dev]"

## Run a suite

    evalgate run suites\support_bot.yaml

Prints one row per case and exits 0 when every case passed, 1 when any case
failed, 2 when the suite could not be loaded.

Only the `fake` provider exists so far. It answers from
`suites\support_bot.responses.yaml`, a mapping of prompt substring to canned
reply, so the whole path runs with zero network calls. Pass `--responses` to
point it at a different file.

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
```

`prompt_template` names a file at `prompts\<name>.txt` next to the suite. The
file must contain the placeholder `{{input}}`, which is replaced with the
case's `input` to form the prompt.

Regex patterns should be single-quoted. YAML processes backslash escapes inside
double quotes, so `"\d+"` is a parse error while `'\d+'` is not.

Unknown keys anywhere in the suite are rejected, so a typo fails at load time
rather than silently passing.

## Development

    pytest
    ruff check .
    ruff format .

The test suite runs entirely against the fake provider.

## Status

Done: models, loader, fake provider, deterministic scorers (`contains`,
`not_contains`, `regex`), async runner with retries and a concurrency limit,
`run` command with a console table.

Not yet: Anthropic provider, `judge` scorer, response cache, baselines and
regression diff, GitHub Actions workflows, demo app.
