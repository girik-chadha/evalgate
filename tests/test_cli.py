import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from evalgate.cli import app

REPO = Path(__file__).resolve().parents[1]
runner = CliRunner()

WRONG_REPLIES = '"return a jacket": "Sorry, no refunds."\n'


@pytest.fixture
def suite(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A private copy of the shipped suite, with the working directory beside it
    so .evalgate state and baselines never land in the repo."""
    shutil.copytree(REPO / "suites", tmp_path / "suites")
    monkeypatch.chdir(tmp_path)
    return Path("suites") / "support_bot.yaml"


def fake_run(suite: Path, *extra: str) -> object:
    return runner.invoke(app, ["run", str(suite), "--provider", "fake", *extra])


def test_fake_run_prints_a_row_per_case_and_exits_zero(suite: Path) -> None:
    result = fake_run(suite, "--no-cache")
    assert result.exit_code == 0, result.output
    for case_id in ("refund_window", "shipping_time", "no_legal_advice"):
        assert case_id in result.output
    assert "3 cases, 3 passed, 0 failed" in result.output
    assert "cache:" not in result.output
    assert "no baseline at" in result.output


def test_second_run_is_served_from_the_cache(suite: Path) -> None:
    first = fake_run(suite)
    second = fake_run(suite)
    assert first.exit_code == 0, first.output
    assert "cache: 0 hits, 6 misses" in first.output
    assert second.exit_code == 0, second.output
    assert "cache: 6 hits, 0 misses" in second.output
    assert Path(".evalgate/cache.db").is_file()


def test_failing_case_exits_one_without_a_baseline(suite: Path, tmp_path: Path) -> None:
    replies = tmp_path / "wrong.yaml"
    replies.write_text(WRONG_REPLIES, encoding="utf-8")
    result = fake_run(suite, "--responses", str(replies), "--no-cache")
    assert result.exit_code == 1
    assert "FAIL" in result.output


def test_baseline_accepts_the_last_run_and_gates_later_runs(
    suite: Path, tmp_path: Path
) -> None:
    assert fake_run(suite).exit_code == 0

    accepted = runner.invoke(app, ["baseline", str(suite)])
    assert accepted.exit_code == 0, accepted.output
    assert "saved" in accepted.output and "3 cases, 3 passed" in accepted.output
    assert (Path("suites") / "support_bot.baseline.json").is_file()

    same = fake_run(suite)
    assert same.exit_code == 0, same.output
    assert "no regression against baseline" in same.output
    assert "3 shared cases" in same.output

    replies = tmp_path / "wrong.yaml"
    replies.write_text(WRONG_REPLIES, encoding="utf-8")
    worse = fake_run(suite, "--responses", str(replies))
    assert worse.exit_code == 1
    assert "regressed" in worse.output
    assert "regression: 3 new failure(s), max 0" in worse.output

    tolerated = fake_run(
        suite,
        "--responses",
        str(replies),
        "--max-new-failures",
        "3",
        "--max-score-drop",
        "1",
    )
    assert tolerated.exit_code == 0, tolerated.output
    assert "no regression against baseline" in tolerated.output


def test_baseline_without_a_recorded_run_exits_two(suite: Path) -> None:
    result = runner.invoke(app, ["baseline", str(suite)])
    assert result.exit_code == 2
    assert "no recorded run" in result.output


def test_explicit_missing_baseline_exits_two(suite: Path) -> None:
    result = fake_run(suite, "--baseline", "nowhere.json")
    assert result.exit_code == 2
    assert "no report at" in result.output


def test_baseline_for_another_suite_is_rejected(suite: Path, tmp_path: Path) -> None:
    assert fake_run(suite).exit_code == 0
    other = tmp_path / "other.json"
    assert (
        runner.invoke(app, ["baseline", str(suite), "--output", str(other)]).exit_code
        == 0
    )
    text = other.read_text(encoding="utf-8").replace('"support_bot"', '"different"', 1)
    other.write_text(text, encoding="utf-8")
    result = fake_run(suite, "--baseline", str(other))
    assert result.exit_code == 2
    assert "baseline for suite 'different'" in result.output


def test_unloadable_suite_exits_two(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("suite: [unclosed", encoding="utf-8")
    result = runner.invoke(app, ["run", str(bad), "--cache", str(tmp_path / "c.db")])
    assert result.exit_code == 2
    assert "invalid YAML" in result.output
    assert not (tmp_path / "c.db").exists()


def test_anthropic_without_api_key_exits_two(
    suite: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    cache = tmp_path / "c.db"
    result = runner.invoke(app, ["run", str(suite), "--cache", str(cache)])
    assert result.exit_code == 2
    assert "ANTHROPIC_API_KEY" in result.output
    assert not cache.exists()


def test_unknown_provider_exits_two(suite: Path) -> None:
    result = runner.invoke(app, ["run", str(suite), "--provider", "openai"])
    assert result.exit_code == 2
    assert "unknown provider" in result.output
