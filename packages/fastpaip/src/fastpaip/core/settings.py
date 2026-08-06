"""The only place this application reads its environment.

Every other module receives what it needs as an argument. That is what makes a
module testable without monkey-patching `os.environ`, and it is what makes the
full set of knobs this deployment has readable in one file rather than
discoverable by grepping for `getenv`.

Values come from environment variables prefixed ``FASTPAIP_`` and from a `.env`
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

ENV_PREFIX = "FASTPAIP_"


class Settings(BaseSettings):
    """Everything this deployment can be configured with.

    Attributes:
        database_url: Defaults to a local SQLite file so a fresh checkout runs
            without configuration. That default is a convenience for
            development and wrong everywhere else — it is deliberately obvious
            in logs rather than clever.
        log_level: Standard logging level name.
    """

    model_config = SettingsConfigDict(
        env_prefix=ENV_PREFIX,
        env_file=".env",
        env_file_encoding="utf-8",
        extra="forbid",
    )

    database_url: str = "sqlite:///./fastpaip.db"
    log_level: str = "INFO"

    @model_validator(mode="after")
    def _reject_unknown_prefixed_variables(self) -> "Settings":
        """Fail startup on a ``FASTPAIP_*`` variable that matches no setting.

        This scans ``os.environ`` by hand, which looks redundant next to
        ``extra="forbid"`` above and is not: that setting only rejects unexpected
        values *passed to the constructor*. Environment variables that match no
        field are never collected by pydantic-settings in the first place, so
        they never reach the extras check — meaning ``extra="forbid"`` alone
        provides exactly no protection against the mistake people actually make.

        The mistake being caught: ``FASTPAIP_DATABSE_URL`` leaves ``database_url``
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
