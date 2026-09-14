from pathlib import Path

import pytest
from typer.testing import CliRunner

from evalgate.cli import app

SUITE = Path(__file__).resolve().parents[1] / "suites" / "support_bot.yaml"
runner = CliRunner()


def test_fake_run_prints_a_row_per_case_and_exits_zero() -> None:
    result = runner.invoke(app, ["run", str(SUITE), "--provider", "fake", "--no-cache"])
    assert result.exit_code == 0, result.output
    for case_id in ("refund_window", "shipping_time", "no_legal_advice"):
        assert case_id in result.output
    assert "3 cases, 3 passed, 0 failed" in result.output
    assert "cache:" not in result.output


def test_second_run_is_served_from_the_cache(tmp_path: Path) -> None:
    cache = tmp_path / "cache.db"
    args = ["run", str(SUITE), "--provider", "fake", "--cache", str(cache)]
    first = runner.invoke(app, args)
    second = runner.invoke(app, args)
    assert first.exit_code == 0, first.output
    assert "cache: 0 hits, 6 misses" in first.output
    assert second.exit_code == 0, second.output
    assert "cache: 6 hits, 0 misses" in second.output
    assert cache.is_file()


def test_failing_case_exits_one(tmp_path: Path) -> None:
    replies = tmp_path / "wrong.yaml"
    replies.write_text('"return a jacket": "Sorry, no refunds."', encoding="utf-8")
    result = runner.invoke(
        app,
        [
            "run",
            str(SUITE),
            "--provider",
            "fake",
            "--responses",
            str(replies),
            "--no-cache",
        ],
    )
    assert result.exit_code == 1
    assert "FAIL" in result.output


def test_unloadable_suite_exits_two(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("suite: [unclosed", encoding="utf-8")
    result = runner.invoke(app, ["run", str(bad), "--cache", str(tmp_path / "c.db")])
    assert result.exit_code == 2
    assert "invalid YAML" in result.output
    assert not (tmp_path / "c.db").exists()


def test_anthropic_without_api_key_exits_two(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    cache = tmp_path / "c.db"
    result = runner.invoke(app, ["run", str(SUITE), "--cache", str(cache)])
    assert result.exit_code == 2
    assert "ANTHROPIC_API_KEY" in result.output
    assert not cache.exists()


def test_unknown_provider_exits_two() -> None:
    result = runner.invoke(app, ["run", str(SUITE), "--provider", "openai"])
    assert result.exit_code == 2
    assert "unknown provider" in result.output
