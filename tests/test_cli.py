from pathlib import Path

from typer.testing import CliRunner

from evalgate.cli import app

SUITE = Path(__file__).resolve().parents[1] / "suites" / "support_bot.yaml"
runner = CliRunner()


def test_run_prints_a_row_per_case_and_exits_zero() -> None:
    result = runner.invoke(app, ["run", str(SUITE)])
    assert result.exit_code == 0, result.output
    for case_id in ("refund_window", "shipping_time", "no_legal_advice"):
        assert case_id in result.output
    assert "3 cases, 3 passed, 0 failed" in result.output


def test_failing_case_exits_one(tmp_path: Path) -> None:
    replies = tmp_path / "wrong.yaml"
    replies.write_text('"return a jacket": "Sorry, no refunds."', encoding="utf-8")
    result = runner.invoke(app, ["run", str(SUITE), "--responses", str(replies)])
    assert result.exit_code == 1
    assert "FAIL" in result.output


def test_unloadable_suite_exits_two(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("suite: [unclosed", encoding="utf-8")
    result = runner.invoke(app, ["run", str(bad)])
    assert result.exit_code == 2
