"""Tests for the one place the environment is read."""

import pytest
from fastpaip.core.settings import Settings
from pydantic import ValidationError


def test_settings_read_the_prefixed_environment(monkeypatch):
    monkeypatch.setenv("FASTPAIP_LOG_LEVEL", "DEBUG")

    assert Settings(_env_file=None).log_level == "DEBUG"


def test_an_unknown_setting_fails_at_startup_rather_than_being_ignored(monkeypatch):
    """A typo in a deployment's environment must not be silently discarded.

    Ignoring extras means `FASTPAIP_DATABSE_URL` leaves the real setting at its
    default — a local SQLite file — and the service starts, serves, and writes
    to the wrong place with nothing in the logs to say so.
    """
    monkeypatch.setenv("FASTPAIP_DATABSE_URL", "postgresql://typo")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_unset_settings_fall_back_to_defaults(monkeypatch):
    monkeypatch.delenv("FASTPAIP_LOG_LEVEL", raising=False)
    monkeypatch.delenv("FASTPAIP_DATABASE_URL", raising=False)

    settings = Settings(_env_file=None)

    assert settings.log_level == "INFO"
    assert settings.database_url.startswith("postgresql+psycopg://")


def test_provider_credentials_in_the_env_file_do_not_break_settings(tmp_path, monkeypatch):
    """The `.env` file is shared with the agent, which needs unprefixed keys.

    `bacteria`'s composition root reads `GEMINI_API_KEY` and
    `ANTHROPIC_API_KEY` from the same file, unprefixed because the provider SDKs
    read those exact names. Under `extra="forbid"` that made this class refuse
    to construct, so adding the key required to run the CLI broke every route,
    task and test that touches settings — and printed the key in the error.

    Anything not starting with the prefix is none of this class's business.
    """
    env = tmp_path / ".env"
    env.write_text(
        "GEMINI_API_KEY=secret-value\nMODEL_PROVIDER=gemini\nFASTPAIP_LOG_LEVEL=DEBUG\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    settings = Settings()

    assert settings.log_level == "DEBUG"
    # The agent's own variable is not adopted: this application names its
    # provider separately, on purpose.
    assert settings.model_provider == "anthropic"


def test_a_typo_in_a_prefixed_variable_is_still_rejected(monkeypatch):
    """Relaxing `extra` must not relax the guard that actually guards.

    `FASTPAIP_DATABSE_URL` leaves `database_url` at its default and the service
    starts happily against the wrong database. That is the mistake people make,
    and it is caught by the hand-written validator rather than by pydantic.
    """
    monkeypatch.setenv("FASTPAIP_DATABSE_URL", "postgresql+psycopg://x/y")

    with pytest.raises(ValidationError, match="DATABSE"):
        Settings()
