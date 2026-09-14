import pytest

from evalgate.config import Settings


def test_api_key_is_read_from_env_and_never_printed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-secret")
    settings = Settings(_env_file=None)
    assert settings.anthropic_api_key is not None
    assert settings.anthropic_api_key.get_secret_value() == "sk-ant-secret"
    assert "sk-ant-secret" not in repr(settings)
    assert "sk-ant-secret" not in str(settings.anthropic_api_key)


def test_missing_api_key_is_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert Settings(_env_file=None).anthropic_api_key is None
