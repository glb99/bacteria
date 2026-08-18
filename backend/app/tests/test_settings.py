"""Tests for the one place the environment is read."""

import logging
import os

import pytest
from pydantic import ValidationError

from bacteria.app.core.settings import Settings, load_env_file


def test_settings_read_the_prefixed_environment(monkeypatch):
    monkeypatch.setenv("BACTERIA_LOG_LEVEL", "DEBUG")

    assert Settings(_env_file=None).log_level == "DEBUG"


def test_an_unknown_setting_fails_at_startup_rather_than_being_ignored(monkeypatch):
    """A typo in a deployment's environment must not be silently discarded.

    Ignoring extras means `BACTERIA_DATABSE_URL` leaves the real setting at its
    default — a local SQLite file — and the service starts, serves, and writes
    to the wrong place with nothing in the logs to say so.
    """
    monkeypatch.setenv("BACTERIA_DATABSE_URL", "postgresql://typo")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_unset_settings_fall_back_to_defaults(monkeypatch):
    monkeypatch.delenv("BACTERIA_LOG_LEVEL", raising=False)
    monkeypatch.delenv("BACTERIA_DATABASE_URL", raising=False)

    settings = Settings(_env_file=None)

    assert settings.log_level == "INFO"
    assert settings.database_url.startswith("postgresql+psycopg://")


def test_provider_credentials_in_the_env_file_do_not_break_settings(tmp_path, monkeypatch):
    """The `.env` file is shared with the agent, which needs unprefixed keys.

    the agent's composition root reads `GEMINI_API_KEY` and
    `ANTHROPIC_API_KEY` from the same file, unprefixed because the provider SDKs
    read those exact names. Under `extra="forbid"` that made this class refuse
    to construct, so adding the key required to run the CLI broke every route,
    task and test that touches settings — and printed the key in the error.

    Anything not starting with the prefix is none of this class's business.
    """
    env = tmp_path / ".env"
    env.write_text(
        "GEMINI_API_KEY=secret-value\nMODEL_PROVIDER=gemini\nBACTERIA_LOG_LEVEL=DEBUG\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    # Named explicitly rather than left to the class default. The suite disables
    # `.env` reading for every other test -- `conftest` says why -- and this is
    # the one test whose subject *is* that file, so it asks for the one it just
    # wrote instead of relying on what the working directory happens to hold.
    settings = Settings(_env_file=env)

    assert settings.log_level == "DEBUG"
    # The agent's own variable is not adopted: this application names its
    # provider separately, on purpose.
    assert settings.model_provider == "anthropic"


def test_a_typo_in_a_prefixed_variable_is_still_rejected(monkeypatch):
    """Relaxing `extra` must not relax the guard that actually guards.

    `BACTERIA_DATABSE_URL` leaves `database_url` at its default and the service
    starts happily against the wrong database. That is the mistake people make,
    and it is caught by the hand-written validator rather than by pydantic.
    """
    monkeypatch.setenv("BACTERIA_DATABSE_URL", "postgresql+psycopg://x/y")

    with pytest.raises(ValidationError, match="DATABSE"):
        Settings()


def test_load_env_file_puts_unprefixed_keys_where_the_sdks_look(tmp_path, monkeypatch):
    """The gap between `Settings` reading `.env` and a provider SDK finding a key.

    The test above proves an unprefixed key in `.env` does not *break* this
    class. This proves the other half, which is the one that bit: pydantic
    reading that file into its own fields puts nothing into `os.environ`, and
    `ANTHROPIC_API_KEY` is read from the real environment by the SDK under that
    exact name. So the service could not reach a model locally while
    `uv run bacteria-agent` could — the agent's composition root called `load_dotenv`
    and no entrypoint here did.
    """
    (tmp_path / ".env").write_text("ANTHROPIC_API_KEY=from-the-file\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    assert Settings().model_provider == "anthropic"
    assert "ANTHROPIC_API_KEY" not in os.environ, "constructing Settings must not export it"

    load_env_file()

    assert os.environ["ANTHROPIC_API_KEY"] == "from-the-file"


def test_the_real_environment_wins_over_the_file(tmp_path, monkeypatch):
    """A container's configuration must not be overridden by a file in the image.

    Same rule `Settings` follows, and the reason it matters more here: this one
    writes into `os.environ`, so getting the precedence backwards would let a
    stale committed `.env` silently replace a deployment's real key.
    """
    (tmp_path / ".env").write_text("ANTHROPIC_API_KEY=from-the-file\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "from-the-environment")

    load_env_file()

    assert os.environ["ANTHROPIC_API_KEY"] == "from-the-environment"


def test_a_setting_without_the_prefix_is_reported(monkeypatch, caplog):
    """The other half of the typo problem, and the one that stays silent.

    `_reject_unknown_prefixed_variables` only inspects names that already start
    with `BACTERIA_`, so it catches a misspelled prefix and cannot see a missing
    one. `RUN_WORKER_IN_API=true` is then never collected, the field keeps its
    `False` default, and the deployment converses perfectly while no job is ever
    consumed — which reads as a broken feature rather than a missing variable.
    It cost an afternoon of production diagnosis exactly once.
    """
    monkeypatch.setenv("RUN_WORKER_IN_API", "true")

    with caplog.at_level(logging.WARNING):
        settings = Settings(_env_file=None)

    assert settings.run_worker_in_api is False, "the unprefixed name must still not be read"
    assert "RUN_WORKER_IN_API" in caplog.text
    assert "BACTERIA_RUN_WORKER_IN_API" in caplog.text


def test_the_platforms_own_database_url_is_not_complained_about(monkeypatch, caplog):
    """Neon and Supabase set a bare `DATABASE_URL` on every deployment.

    Warning about it would fire on every correctly configured production boot,
    which is how a warning stops being read — and it would take this one's real
    cases with it.
    """
    monkeypatch.setenv("DATABASE_URL", "postgresql://set-by-the-integration")

    with caplog.at_level(logging.WARNING):
        Settings(_env_file=None)

    assert "DATABASE_URL" not in caplog.text
