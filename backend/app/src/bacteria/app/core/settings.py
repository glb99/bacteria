"""The only place this application reads its environment.

Every other module receives what it needs as an argument. That is what makes a
module testable without monkey-patching `os.environ`, and it is what makes the
full set of knobs this deployment has readable in one file rather than
discoverable by grepping for `getenv`.

Values come from environment variables prefixed ``BACTERIA_`` and from a `.env`
file, in that order — the environment wins, so a container's configuration is
never silently overridden by a file someone left in the image. A prefixed
variable matching no setting is a startup failure rather than a shrug; see
:meth:`Settings._reject_unknown_prefixed_variables` for why that needs writing
by hand.

Note the boundary with the agent. ``bacteria`` reads its own environment in its
own composition root, for running standalone; that is not this file's business
and this file does not reach into it. When the application composes the agent,
it passes values explicitly rather than relying on a variable both happen to
read — two packages sharing an environment variable by coincidence is a coupling
that no import graph would show you.

Not built:
    Secrets handling. ``database_url`` will carry a password and is a plain
    ``str``, so it can be printed, logged, or serialized into an error page by
    anything holding it. A real deployment wants ``SecretStr`` here and a rule
    about what may be logged; both are cheap to add and neither is done.

    Per-environment profiles. There is one settings class, not one per
    environment. Whatever differs between development and production differs by
    variable, which is enough until something needs to differ by *shape*.
"""

import os
from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_PREFIX = "BACTERIA_"

ENV_FILE = ".env"
"""The dotenv file, named once so the two readers of it cannot drift apart.

:class:`Settings` reads it for its own prefixed values; :func:`load_env_file`
reads it into the process environment for the provider SDKs. Both resolve it
relative to the working directory.
"""


class Settings(BaseSettings):
    """Everything this deployment can be configured with.

    Attributes:
        database_url: Defaults to the Postgres in ``docker-compose.yml``, so
            development runs on the database production uses. It was a local
            SQLite file for a while, and that hid two things: SQLite has no
            ``SKIP LOCKED``, which the job queue needs, and its DDL differs
            enough that a migration could pass in development and fail in
            production. The driver must be an async one; a synchronous URL
            fails at engine creation rather than at first query, which is where
            you want it.

            One driver, ``psycopg`` 3, is used for both SQLAlchemy and the job
            queue. Procrastinate requires psycopg, and running asyncpg
            alongside it would mean two Postgres drivers, two connection pools,
            and two sets of behaviour to know about, for a difference in speed
            nothing here can currently measure.
        log_level: Standard logging level name.
        model_provider: Which model backs the agent. Named here rather than read
            from the agent's own ``MODEL_PROVIDER`` because this application
            composes the agent explicitly — two packages agreeing on an
            environment variable is a coupling no import graph would reveal.
            Provider *credentials* are not here: the SDKs read their own
            variables, and routing a secret through this class would mean
            holding it in a place with no reason to.
    """

    model_config = SettingsConfigDict(
        env_prefix=ENV_PREFIX,
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        # ``ignore``, not ``forbid``, and this is not a weakening of the guard.
        # The guard is :meth:`_reject_unknown_prefixed_variables` below, written
        # by hand precisely because ``forbid`` never caught an unknown
        # environment variable to begin with.
        #
        # What ``forbid`` did catch was every *unrelated* key in the ``.env``
        # file, which is shared. The agent's composition root reads that file
        # for ``GEMINI_API_KEY`` and ``ANTHROPIC_API_KEY`` — unprefixed by
        # necessity, because provider SDKs read those exact names. So adding the
        # key needed to run ``uv run bacteria`` made this class refuse to
        # construct, and every route, task and test that touches settings failed
        # at once. Worse, the validation error printed the key.
        extra="ignore",
    )

    database_url: str = "postgresql+psycopg://bacteria:bacteria@localhost:5432/bacteria"
    log_level: str = "INFO"
    model_provider: str = "anthropic"

    @model_validator(mode="after")
    def _reject_unknown_prefixed_variables(self) -> "Settings":
        """Fail startup on a ``BACTERIA_*`` variable that matches no setting.

        This scans ``os.environ`` by hand, which looks redundant next to
        ``extra="forbid"`` above and is not: that setting only rejects unexpected
        values *passed to the constructor*. Environment variables that match no
        field are never collected by pydantic-settings in the first place, so
        they never reach the extras check — meaning ``extra="forbid"`` alone
        provides exactly no protection against the mistake people actually make.

        The mistake being caught: ``BACTERIA_DATABSE_URL`` leaves ``database_url``
        at its default, and the service starts happily and writes to a local
        SQLite file with nothing in the logs to say why.
        """
        known = {f"{ENV_PREFIX}{name}".upper() for name in type(self).model_fields}
        unknown = sorted(
            name
            for name in os.environ
            if name.upper().startswith(ENV_PREFIX) and name.upper() not in known
        )
        if unknown:
            raise ValueError(
                f"unrecognized {ENV_PREFIX}* environment variable(s): {', '.join(unknown)}"
            )
        return self


def load_env_file() -> None:
    """Load `.env` into the process environment. Call from an entrypoint only.

    :class:`Settings` already reads `.env` for its own ``BACTERIA_*`` values, so
    this is not about configuration reaching this class. It is about the values
    that never do: provider SDKs read ``ANTHROPIC_API_KEY`` and
    ``GEMINI_API_KEY`` from the real environment, under those exact unprefixed
    names, and pydantic-settings reading a file into *its own* fields puts
    nothing into ``os.environ`` for them to find.

    So the service could not reach a model locally without an operator exporting
    keys by hand, while ``uv run bacteria`` worked — because the agent's own
    composition root called this and no entrypoint here did. The asymmetry was
    invisible in the code and immediate the first time anyone served a turn.

    A function called from an entrypoint rather than an import side effect.
    Loading a file on import would mutate the environment of anything that
    imported anything downstream, test collection included, which is the property
    :func:`get_settings` is shaped to avoid.

    Existing variables win, matching :class:`Settings` and for the same reason: a
    container's configuration must not be overridden by a file left in an image.

    The path is given explicitly rather than discovered. Bare ``load_dotenv()``
    searches *upward from the calling module's own file*, so it would resolve
    relative to this package's location on disk while ``Settings(env_file=ENV_FILE)``
    resolves relative to the working directory — two mechanisms that agree until
    a process is started from somewhere unexpected and then load different files.
    One of them being right and the other subtly wrong is worse than either.
    """
    from dotenv import load_dotenv

    load_dotenv(dotenv_path=ENV_FILE, override=False)


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings, constructed once.

    Cached because reading and validating the environment repeatedly is waste,
    and because two callers disagreeing about configuration mid-process is a
    class of bug worth making impossible.

    A function rather than a module-level instance so that importing this module
    has no side effect: a module-level ``settings = Settings()`` would make every
    import of anything downstream fail on a machine with a bad environment,
    including during test collection.
    """
    return Settings()
