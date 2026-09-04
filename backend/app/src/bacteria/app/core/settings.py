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

import logging
import os
from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

ENV_PREFIX = "BACTERIA_"

UNPREFIXED_AND_NOT_OURS = frozenset({"DATABASE_URL"})
"""Unprefixed names that belong to someone else and must not be complained about.

``DATABASE_URL`` is set by the Neon and Supabase integrations on every deployment
that uses one, and `docs/guides/deployment.md` already tells the operator this
application ignores it in favour of the prefixed copy. Warning about it would
fire on every correctly configured production boot — the failure the ASGI
lifespan describes at length, where a warning that fires when nothing is wrong
teaches people to scroll past the ones that mean something.
"""

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
        run_worker_in_api: Run the job worker inside the API process instead of
            as ``bacteria-worker``.

            **False by default, and that default is the honest one.** A worker
            and the API fail differently, scale differently, and a job that
            saturates the loop should not be able to make the API unresponsive —
            which is why they are two commands. Turning this on gives that up.

            It exists because a single-process platform is a real deployment
            target and the alternative there is worse: with no worker anywhere,
            ``POST /ingestion/batches:defer`` answers ``202`` for work nothing
            will ever perform, which is a route that lies. A degraded separation
            beats a silent drop. See
            [ADR 0001](../../../../../docs/adr/0001-run-the-worker-in-the-api-process.md).

            Leave it off anywhere you can run two processes — ``just stack``,
            Docker Compose, or a host with a worker service.
        worker_concurrency: How many jobs the in-process worker runs at once.
            Ignored unless ``run_worker_in_api`` is set. Lower than the standalone
            worker's default would be defensible, since here it competes with
            request handling for one event loop.
        memory_extraction_enabled: Whether a turn queues a job to read the new
            transcript items and *propose* memories from them.

            **Off by default**, and for the same kind of reason as
            ``run_worker_in_api``: it costs a model call per turn, roughly
            doubling per-turn spend, for a feature whose output nothing surfaces
            yet. A deployment should turn this on having decided to pay for it,
            not discover it on a bill. Nothing it produces can reach a model
            without a human activating it, so the risk of leaving it on is
            expense and review backlog rather than behaviour.
        graph_backed_memory: Whether keyed memory is read from and written to the
            assertion graph instead of ``chat_memory_entry`` and its siblings.

            **Off by default**, and a whole-deployment choice rather than a
            per-request one. A store selected per call would make "which memory
            answered" unanswerable exactly when the two disagree, which is the
            question this setting exists to let somebody ask.

            On, memory is **thinner, not empty**: extraction proposes
            preferences the catalogue knows and the owner confirms them, so a
            deployment that flips this keeps what has been confirmed and loses
            every key the graph's vocabulary has no relation for — ``user_name``
            among them, which is the one worth knowing about before flipping it.
            That is why the default is still the store that takes any key.

        graph_retrieval_enabled: Whether the graph decides which memories a turn
            is shown, by resolving the message to nodes and returning the
            confirmed claims about them.

            **Off by default, and the default is doing work.** With nothing
            confirmed the graph narrows to an empty set, so a deployment that
            turned this on before curating anything would lose its memory and
            read it as retrieval failing rather than as there being nothing to
            retrieve.

            Separate from ``graph_backed_memory``: one decides where a keyed
            memory *lives*, the other decides which memories are *surfaced*, and
            a deployment may sensibly want either without the other.

        graph_extraction_enabled: Whether a turn queues a job to read the new
            transcript items and record *relationships* from them in the memory
            graph.

            **Off by default**, and separately from ``memory_extraction_enabled``
            rather than beside it. They are two model calls with two costs, and a
            deployment that wants suggested facts reviewed by a person does not
            thereby want a graph built — nor the reverse. One flag would make
            turning either on a decision about both.

            Nothing it writes reaches a model. An assertion may influence which
            already-confirmed memories are surfaced and never contributes text,
            so the risk of leaving this on is expense rather than behaviour.
        graph_extraction_model: Which model records relationships, or ``None`` for
            the provider's default. Separate from ``memory_extraction_model``
            because the two prompts fill different schemas and may want different
            models; the provider is shared.
        graph_extraction_max_assertions: The most claims one run may record.
            Higher than the proposal cap because nothing here waits for a person
            — the bound is on a model's enthusiasm rather than on a review queue.
        memory_extraction_model: Which model performs the extraction, or ``None``
            for the provider's default.

            Separate from ``model_provider``'s default model because these are
            different jobs: the agent's is conversational, this one fills a small
            JSON schema from a bounded transcript slice, which the cheapest model
            a provider offers does well. The provider is shared; only the model
            differs.
        logfire_token: Where traces go. **Empty is not an error**, and that is
            the one exception to this class's "an unrecognised ``BACTERIA_``
            variable refuses to boot" strictness. Absent, the process prints
            spans to the console instead of exporting them — a development
            machine with no observability vendor is the ordinary case, and
            refusing to start there would make every contributor configure one
            before running anything. See ADR 0003.
        logfire_environment: Which deployment produced a trace. Kept separate
            from the token so that two deployments sharing one project stay
            distinguishable.
        logfire_console: Whether spans are also printed to stdout. ``None``, the
            default, means *print only when there is no token* — see
            :func:`bacteria.app.core.observability._should_print_spans` for why
            that is the honest default rather than a preference.

            Set it to ``true`` to get both, which is a real local case: a
            developer holding a token may still want spans in the terminal. Set
            it to ``false`` to silence them even with no exporter configured.

            It cannot put spans back into ``bacteria-admin``'s stdout. That
            surface opts out in code, because its output is a conversation
            rather than a log, and a deployment variable must not be able to
            override a property of what the stream *is*.
        memory_extraction_max_proposals: The most proposals one extraction run
            may write.

            A bound the agent's ADR 0017 named and did not build: proposals cost
            nothing in the prompt and everything in the review surface, and a
            session accumulating thousands of them makes the queue useless
            without anything looking broken. Applied to the model's output rather
            than to the table, so the excess is dropped and counted at the point
            something can say it happened.
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
    run_worker_in_api: bool = False
    worker_concurrency: int = 4
    memory_extraction_enabled: bool = False
    graph_backed_memory: bool = False
    graph_retrieval_enabled: bool = False
    graph_extraction_enabled: bool = False
    graph_extraction_model: str | None = None
    graph_extraction_max_assertions: int = 8
    memory_extraction_model: str | None = None
    memory_extraction_max_proposals: int = 5
    logfire_token: str = ""
    logfire_environment: str = "local"
    logfire_console: bool | None = None

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

    @model_validator(mode="after")
    def _warn_about_settings_missing_the_prefix(self) -> "Settings":
        """Warn when a setting's own name is set *without* ``BACTERIA_``.

        The other direction of the same mistake, and invisible to the check
        above: that one inspects only names already starting with the prefix, so
        ``BACTERIA_RUN_WORKER_IN_APII`` refuses to boot in a second while
        ``RUN_WORKER_IN_API`` is never collected, never mentioned, and leaves the
        field at its default. The service then runs perfectly with no worker,
        conversing normally while no proposal ever appears. That is not
        hypothetical — it cost an afternoon of production diagnosis on
        2026-08-18, and the log line that finally identified it was about the
        consequence rather than the cause.

        Warns rather than raising, which is the difference between the two
        checks and not an inconsistency. A ``BACTERIA_*`` variable matching no
        field is always a mistake, because nothing else uses that prefix. An
        unprefixed one is not ours to judge: see :data:`UNPREFIXED_AND_NOT_OURS`.
        Refusing to start on a name the platform legitimately set would turn a
        working deployment into a crash loop.
        """
        fields = {name.upper() for name in type(self).model_fields}
        for name in sorted(os.environ):
            upper = name.upper()
            if upper in fields and upper not in UNPREFIXED_AND_NOT_OURS:
                logger.warning(
                    "%s is set but nothing reads it; every setting here is "
                    "prefixed — did you mean %s%s?",
                    name,
                    ENV_PREFIX,
                    upper,
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
