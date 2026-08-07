"""Tests for the one place the environment is read."""

import pytest
from pydantic import ValidationError

from fastpaip.core.settings import Settings


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
