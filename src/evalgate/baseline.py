from pathlib import Path

from pydantic import ValidationError

from evalgate.errors import EvalgateError
from evalgate.models import RunReport


class BaselineError(EvalgateError):
    pass


def baseline_path(suite_path: Path) -> Path:
    return suite_path.with_name(f"{suite_path.stem}.baseline.json")


def last_run_path(runs_dir: Path, suite_name: str) -> Path:
    return runs_dir / f"{suite_name}.json"


def save_report(report: RunReport, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report.model_dump_json(indent=2), encoding="utf-8")


def load_report(path: Path) -> RunReport:
    if not path.is_file():
        raise BaselineError(f"no report at {path}")
    try:
        return RunReport.model_validate_json(path.read_text(encoding="utf-8"))
    except ValidationError as e:
        raise BaselineError(f"{path}: not a valid report: {e}") from e
