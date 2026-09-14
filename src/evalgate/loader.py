from pathlib import Path

import yaml
from pydantic import ValidationError

from evalgate.errors import EvalgateError
from evalgate.models import Suite

PLACEHOLDER = "{{input}}"


class SuiteError(EvalgateError):
    """The suite or its prompt templates cannot be used. Message is user-facing."""


def load_suite(path: Path) -> Suite:
    try:
        return Suite.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    except yaml.YAMLError as e:
        raise SuiteError(f"{path}: invalid YAML: {e}") from e
    except ValidationError as e:
        raise SuiteError(f"{path}: {e}") from e


def load_templates(suite: Suite, suite_dir: Path) -> dict[str, str]:
    """Read prompts/<name>.txt for every template the suite names."""
    templates: dict[str, str] = {}
    for name in sorted({case.prompt_template for case in suite.cases}):
        path = suite_dir / "prompts" / f"{name}.txt"
        if not path.is_file():
            raise SuiteError(f"prompt template {name!r} not found at {path}")
        text = path.read_text(encoding="utf-8")
        if PLACEHOLDER not in text:
            raise SuiteError(f"{path}: no {PLACEHOLDER} placeholder")
        templates[name] = text
    return templates


def render_prompt(template: str, input: str) -> str:
    return template.replace(PLACEHOLDER, input)
