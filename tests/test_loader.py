from pathlib import Path

import pytest

from evalgate.loader import SuiteError, load_suite, load_templates, render_prompt
from evalgate.models import JudgeAssertion

REPO = Path(__file__).resolve().parents[1]

EXAMPLE_SUITE = """suite: support_bot
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
      - type: judge
        criterion: "States the refund window and offers a next step"
        min_score: 0.7
"""


def write_suite(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "suite.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_parses_the_example_suite(tmp_path: Path) -> None:
    suite = load_suite(write_suite(tmp_path, EXAMPLE_SUITE))
    assert suite.name == "support_bot"
    assert suite.model == "claude-sonnet-4-5"
    (case,) = suite.cases
    assert case.id == "refund_window"
    assert [a.type for a in case.assertions] == ["contains", "not_contains", "judge"]
    judge = case.assertions[2]
    assert isinstance(judge, JudgeAssertion)
    assert judge.min_score == 0.7


def test_misspelt_key_is_rejected(tmp_path: Path) -> None:
    text = EXAMPLE_SUITE.replace('value: "30 days"', 'vlaue: "30 days"')
    with pytest.raises(SuiteError, match="vlaue"):
        load_suite(write_suite(tmp_path, text))


def test_unknown_assertion_type_is_rejected(tmp_path: Path) -> None:
    text = EXAMPLE_SUITE.replace("type: contains", "type: shouts")
    with pytest.raises(SuiteError, match="shouts"):
        load_suite(write_suite(tmp_path, text))


def test_invalid_yaml_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(SuiteError, match="invalid YAML"):
        load_suite(write_suite(tmp_path, "suite: [unclosed"))


def test_duplicate_case_ids_are_rejected(tmp_path: Path) -> None:
    case_block = EXAMPLE_SUITE.split("cases:\n")[1]
    with pytest.raises(SuiteError, match="duplicate case id"):
        load_suite(write_suite(tmp_path, EXAMPLE_SUITE + case_block))


def test_templates_load_and_render(tmp_path: Path) -> None:
    suite = load_suite(write_suite(tmp_path, EXAMPLE_SUITE))
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts" / "support_v2.txt").write_text(
        "Q: {{input}}", encoding="utf-8"
    )
    templates = load_templates(suite, tmp_path)
    assert render_prompt(templates["support_v2"], "hello") == "Q: hello"


def test_missing_template_is_rejected(tmp_path: Path) -> None:
    suite = load_suite(write_suite(tmp_path, EXAMPLE_SUITE))
    with pytest.raises(SuiteError, match="support_v2"):
        load_templates(suite, tmp_path)


def test_template_without_placeholder_is_rejected(tmp_path: Path) -> None:
    suite = load_suite(write_suite(tmp_path, EXAMPLE_SUITE))
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts" / "support_v2.txt").write_text(
        "no placeholder here", encoding="utf-8"
    )
    with pytest.raises(SuiteError, match="placeholder"):
        load_templates(suite, tmp_path)


def test_shipped_suite_loads() -> None:
    suite = load_suite(REPO / "suites" / "support_bot.yaml")
    templates = load_templates(suite, REPO / "suites")
    assert {c.prompt_template for c in suite.cases} <= set(templates)
