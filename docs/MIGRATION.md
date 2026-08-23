# Target structure and migration plan

**A historical record.** Every step below is done, and this file is kept for the
reasoning attached to each — what was tried, what was rejected, and what a
decision cost. It is not a description of the current tree; the
[README](../README.md) is.

Package names were updated in place when `bacteria-app` became `bacteria.app` and
`bacteria` became `bacteria.agent`, so that a reader is not made to hold a
retired vocabulary just to follow the argument. Quoted `pyproject.toml` excerpts
are therefore not literal transcripts of what was committed at the time.

What this repository is: a uv workspace holding two packages — the agent
(`bacteria-agent`) and the application that hosts it (`bacteria-app`), both under
`backend/`, alongside a `frontend/` that does not exist yet.

## Step 0 — put this under version control *(done)*

There is no `.git` here. Everything in this tree is unversioned, including work
that took real effort. Before any file moves:

```bash
git init && git add -A && git commit -m "Import current state before restructure"
```

The rest of this plan moves and deletes files. Doing that without a commit to
return to is the only genuinely reckless part of it.

## Target tree *(steps 3-4 realize the skeleton; feature packages are not created yet)*

```
bacteria/
  pyproject.toml                 workspace root; builds nothing
  uv.lock                        one lockfile for both packages
  Justfile
  .envrc  .gitignore  LICENSE  README.md
  docs/
    MIGRATION.md                 this file
  packages/
    agent/                       the agent — vendored whole, its own package
      pyproject.toml
      src/bacteria/agent/        imports: `from bacteria...`
      tests/
      docs/adr/
      CLAUDE.md  README.md
    app/                         the application
      pyproject.toml
      src/bacteria/app/
        core/                    cross-cutting infrastructure
          __init__.py
          protocols.py           the Processable step contract
          handlers.py            Chain of Responsibility
          adapters.py            FunctionalProcessor
          settings.py            pydantic-settings; the only env reader
          db.py                  engine + session factory
          logging.py             structured logging setup
        ingestion/               feature: models, repositories, services,
          __init__.py            steps (handler chain), views
        audio/                   feature: real-time streaming
          __init__.py
        chat/                    feature: hosts the agent
          __init__.py
          session_repository.py  persistent SessionStore implementation
          approval.py            out-of-band approval implementation
          views.py
        entrypoints/             configuration only; no logic; no coverage
          __init__.py
          asgi.py
          worker.py
          cli.py
      tests/
        core/  ingestion/  audio/  chat/
```

## The pyproject files

### Root — `pyproject.toml`

Builds nothing. It exists to declare the workspace and hold the shared dev
toolchain.

```toml
[project]
name = "bacteria-workspace"
version = "0"
requires-python = ">=3.13"
dependencies = []

[tool.uv]
package = false

[tool.uv.workspace]
members = ["backend/*"]

[dependency-groups]
dev = [
    "pytest>=8.3",
    "pytest-asyncio>=0.24",
    "anyio>=4.6",
    "coverage>=7.6",
    "fastapi[standard]",
]

[tool.coverage.run]
branch = true
parallel = true
source = ["bacteria.app"]

[tool.coverage.report]
show_missing = true
skip_covered = true
omit = ["**/entrypoints/*"]
```

Two things in there are deliberate and worth not undoing.

`source = ["bacteria.app"]` excludes `bacteria`. The agent's test suite is
[architectural fitness functions by design](../backend/agent/docs/adr/0013-test-load-bearing-invariants-only.md) —
uneven coverage is the stated intent, and pointing a coverage report at it will
produce a number that invites someone to "fix" it by writing the tests that ADR
exists to decline. The application gets measured; the agent does not.

`omit = ["**/entrypoints/*"]` replaces the current `omit = ["src/**/asgi.py"]`,
matching your rule that entrypoints hold configuration only. If an entrypoint
ever contains something worth testing, that is the signal it contains logic that
belongs elsewhere.

### `backend/agent/pyproject.toml`

Unchanged from the agent's current file, except that `pytest-asyncio` joins the
dev extra once [ADR 0014](../backend/agent/docs/adr/0014-async-at-the-io-boundaries.md)
lands.

```toml
[project]
name = "bacteria-agent"
version = "0.1.0"
description = "A small AI agent built as infrastructure: layered ownership boundaries, kept minimal enough to read."
requires-python = ">=3.11"
dependencies = [
    "anthropic>=0.40.0",
    "google-genai>=1.0.0",
    "pydantic>=2.9.0",
    "python-dotenv>=1.0.0",
    "stamina>=24.3",
]

[project.optional-dependencies]
dev = ["pytest>=8.3.0", "pytest-asyncio>=0.24"]

[project.scripts]
bacteria = "bacteria.agent.interfaces.cli:main"

[build-system]
requires = ["uv_build>=0.11,<0.12"]
build-backend = "uv_build"

[tool.pytest.ini_options]
minversion = "8.3"
testpaths = ["tests"]
addopts = ["-ra", "--strict-markers", "--strict-config", "--import-mode=importlib"]
```

`requires-python` stays `>=3.11`. The application pins tighter; a lower bound on
the library costs nothing and keeps it vendorable elsewhere.

### `backend/app/pyproject.toml`

```toml
[project]
name = "bacteria-app"
version = "0"
requires-python = ">=3.13"
dependencies = [
    "bacteria-agent",
    "fastapi",
    "granian",
    "sqlmodel",
    "alembic",
    "pydantic-settings",
    "stamina",
]

[tool.uv.sources]
bacteria-agent = { workspace = true }

[build-system]
requires = ["uv_build>=0.11,<0.12"]
build-backend = "uv_build"

[tool.pytest.ini_options]
minversion = "8.3"
testpaths = ["tests"]
asyncio_mode = "auto"
```

The current file's `name = "hello-svc"` and its missing `sqlmodel` are both
fixed here. `requires-python` moves from `==3.13.*` to `>=3.13` — the hard pin
excludes 3.14, which is what the agent's virtualenv is currently running.

## What moves where

| Today | Target | Note |
|---|---|---|
| `src/agent/` (an earlier broken copy) | *delete* | Broken copy — the directory was renamed but every internal import still says `from bacteria...`. Replaced by the real package. |
| `tests/agent/` | *delete* | Ships with the package. |
| `src/protocols.py` | `core/protocols.py` | Trimmed — see below. Trimmed again since, to `Processable` alone. |
| `src/handlers.py` | `core/handlers.py` | Two fixes — see below. |
| `src/adapters.py` | `core/adapters.py` | As-is. |
| `src/bacteria/app/models.py` | *deleted* | Held `User` alone, which was template scaffolding rather than a feature: nothing mounted a router for it and no credential ever resolved to a row. Deleted with the `user` table in `a3f81c60b204` — the name read as the accounts table this application deliberately does not have. |
| `src/bacteria/app/repositories.py` | *deleted* | Went with `models.py`, taking the last synchronous repository and the `sync_session` fixture with it. Worth keeping the reason it survived so long: it had **no imports at all**, and on Python 3.13 that raised `NameError` at import — but PEP 649 defers annotation evaluation from 3.14, so it began importing cleanly and would have failed at the first *call* instead. |
| `src/bacteria/app/services.py` | per feature | Empty today. |
| `src/bacteria/app/dependencies.py` | `core/dependencies.py` | Empty today. |
| `src/bacteria/app/views.py` | `<feature>/views.py` | The `/` hello route becomes a health check. |
| `src/bacteria/app/entrypoints/asgi.py` | `entrypoints/asgi.py` | Add the missing `__init__.py`. |
| `tests/test_e2e.py` | `backend/app/tests/` | |
| `Justfile` | root, edited | Three stale `hello_svc` references break `just serve` and `just cov`. |
| `README.md` | rewrite | Currently a link to the uv video the template came from. |

### Changes to the moved framework files

**`core/protocols.py`** — drop `Repository` and `CRUDRepository`. The first is
an empty marker interface, which structural typing makes unnecessary. The second
recombines the four segregated protocols into the god-interface that segregating
them was meant to avoid; compose the two or three a given repository actually
needs at its definition instead.

**Since then, the four segregated protocols went too**, and the reason is more
interesting than the one above. `CanRead`, `CanCreate`, `CanUpdate` and
`CanDelete` were not too coarse — they were the wrong shape. Every repository
this application grew declined them: `ApiKeyRepository` revokes rather than
deletes, `SqlSessionRepository` has no `update` by design, `IngestionRepository`
persists. Their only implementer was the template's `UserRepository`, deleted
with the `user` table in `a3f81c60b204`, and no signature anywhere was ever
annotated with one. `core/protocols.py` keeps the full account.

**`core/handlers.py`** — two fixes. `_next_handler` is declared as a class
attribute and works only because `set_next` shadows it on the instance; move it
into `__init__`. And replace the two `print()` calls with structured logging — a
skipped step should leave a record of *why* it was skipped, which
`can_handle` returning a bare `False` currently discards.

## What changes in bacteria

Three things, in dependency order.

**1. Async at the I/O boundaries.** Already decided and recorded as
[ADR 0014](../backend/agent/docs/adr/0014-async-at-the-io-boundaries.md).
This has to land first — every item below is written against the async shape.

**2. Persistence arrives by dependency inversion.** `session/store.py` names its
own gap: persistence is "a second implementation of this class, not a change to
any caller." The application supplies that implementation
(`chat/session_repository.py`, SQLModel-backed), and bacteria declares the
protocol it must satisfy.

The direction matters. Bacteria declares `SessionRepository`; the application
implements it. Bacteria never imports SQLModel, and the agent stays vendorable
into a project that uses something else entirely.

That protocol is **not** `CRUDRepository`. `SessionStore` exposes
`create_session` / `get_state` / `commit` / `remember` / `forget` — deliberately
no `update`, because an update method is a second write path and
[ADR 0004](../backend/agent/docs/adr/0004-single-commit-path.md) exists to
guarantee there is exactly one.

> The last sentence here used to read "The generic CRUD protocols serve the
> application's own entities, where CRUD genuinely is the shape." That was
> wrong, and it is left visible because the mistake is instructive: the CRUD
> shape was assumed to fit the *application* because it did not fit the agent.
> It fit neither. Every repository the application grew has domain verbs, and
> the protocols were deleted rather than implemented.

**3. Approval becomes an awaitable decision, not a prompt.**
`tools/approval.py` reads stdin. That cannot exist in a request handler or a
queue worker. It becomes an async protocol with two implementations: the
existing interactive one for the CLI, and a persisted pending-approval record
for the service, which the turn awaits and a later HTTP call resolves.

That second implementation needs the agent to be able to pause and resume a
turn — which is exactly the *session routing / resume* gap `session/store.py`
already documents as deferred. Ingestion and audio will force it; it is worth
knowing now that approval is what drags it in, and that it needs its own ADR.

### What does *not* change: the two composition roots

Correcting something I said earlier — `bacteria.agent.interfaces` and
`bacteria.app.entrypoints` do not actually collide. They compose different
processes. The agent keeps `interfaces/cli.py` and stays independently runnable
via `uv run bacteria`, which is worth preserving: it is the reference
implementation of how the layers wire together, and the thing you can run to
check the agent still works without standing up a web service.

The rule that keeps them from colliding is one line: **the application never
imports `bacteria.agent.interfaces`.** It composes `Runtime`, a model client, a
registry, and a store itself, in `entrypoints/`. Provider selection exists in
both places because both are entry points into the same library — that is what
an entry point is for.

## Order of work

1. ~~`git init` and commit the current state.~~ **Done.**
2. ~~Async refactor in bacteria.~~ **Done** — 60 tests, one live Gemini
   tool-calling turn verified end to end.
   ([ADR 0014](../backend/agent/docs/adr/0014-async-at-the-io-boundaries.md).)
3. ~~Create the workspace skeleton; move bacteria in.~~ **Done** — brought in
   with `git subtree`, so its history came along rather than arriving as an
   anonymous copy. `just test` runs both suites; `just agent` runs the CLI.
4. ~~Repair the framework files in `core/`; add `settings.py`; fix
   `repositories.py`.~~ **Done.** 14 application tests, `just cov` working.
   One correction found along the way: `extra="forbid"` does *not* reject
   unknown environment variables — pydantic-settings never collects prefixed
   variables that match no field, so they never reach the extras check. The
   guard is written by hand in `Settings._reject_unknown_prefixed_variables`.
5. ~~First feature end to end, `chat/`.~~ **Done.** The agent declares
   `SessionRepository` (bacteria ADR 0015) and `chat/` implements it against
   SQLModel; a conformance suite runs the same ten behaviours against both
   implementations. Routes create a session, take a turn, and read a
   transcript. Alembic is **not** done — `create_all` stands in, with the gap
   recorded in `core/db.py`.

   Two things deferred deliberately, both recorded where they would be filled:
   tools are not offered over HTTP, because approval has nobody to ask until
   runs can pause and resume; and the SQL repository was async over synchronous
   queries, which blocked the loop. *(That second one is now fixed — see step
   7.)*
6. ~~Ingestion.~~ **Done**, as generic record ingestion: a validate →
   normalize → persist chain built from `core.handlers`, which is the first
   real use of that machinery. Rejections are stored, not counted.

   Deferred and recorded where they would go: background execution
   (`entrypoints/queue_worker.py` is a documented stub — the open question is
   which broker and whether jobs survive a restart, and batches are capped at
   500 inline in the meantime), and cross-batch duplicate handling, which needs
   someone to choose between "update the existing row" and "reject the new
   one".

7. ~~Make the persistence layer genuinely async.~~ **Done.** The repositories
   were `async def` around synchronous SQLModel calls — async's shape without
   async's benefit. Now an async engine, `AsyncSession`, and awaited queries
   throughout. The handler chain went async too, since a synchronous chain
   meant ingestion could never be non-blocking by any change confined to its
   repository; steps may still be written either way, and a plain function is
   run in a worker thread.

   Measured rather than assumed: a heartbeat ticking on the event loop during
   200 sequential commits saw a worst-case gap of 6.5ms, so the loop stays
   free.

   Note what this buys per backend. SQLite has no async C API, so `aiosqlite`
   moves the blocking to a worker thread rather than removing it. `asyncpg` is
   genuinely non-blocking, and that is the production target.

8. ~~Authentication and authorization.~~ **Done.** API keys, hashed at rest,
   issued by an operator CLI rather than an endpoint — minting credentials over
   HTTP needs a credential, and the first one has nowhere to come from. Every
   route now requires a principal, sessions are owned by the principal that
   created them, and the owner can no longer be named by the client.

   The two halves are separate packages on purpose: `auth/` establishes who,
   `chat/access.py` establishes whether. Not-yours returns 404 rather than 403,
   so a session id cannot be probed for existence.

   Still open: key scopes and expiry, and tenancy for ingested records.

9. ~~Migrations.~~ **Done.** Alembic owns the schema. Nothing creates tables at
   startup any more — the server does not, and the admin CLI stopped doing so
   too, since a tool that quietly builds a database when pointed at an empty one
   will eventually be pointed at the wrong one.

   The part worth keeping is `test_migrations.py`: it replays every migration
   and asserts no autogenerate diff against the models. Without it, the drift
   is silent in exactly the wrong direction — tests build from the models and
   pass, while production is missing a column. It was verified by adding a
   field without a migration and watching it fail.

   It earned its keep immediately: it found that the leftover `User` model from
   the template had never been in any migration.

10. ~~Background worker.~~ **Done.** Postgres as the queue via procrastinate,
    chosen for transactional enqueue: a job commits with the data change that
    justifies it, so the "row saved, job lost" window a broker leaves does not
    exist. Development moved onto Postgres in the same step, which is what
    `docker-compose.yml` is for.

11. ~~Put the tests on the database we deploy on.~~ **Done.** Six test files
    each built their own in-memory SQLite engine; only migrations and settings
    used Postgres. `tests/conftest.py` now owns one throwaway database per run,
    truncated between tests, and SQLite is gone entirely — `aiosqlite` with it.

    It was not a tidying exercise. SQLite ignores `DateTime(timezone=True)` and
    returns naive datetimes, so `_tz_column()` — which every model uses,
    including `ApiKey.revoked_at` — round-tripped differently under test than in
    production, and any comparison against an aware `datetime.now(timezone.utc)`
    raises `TypeError` on exactly one of them. There is now a test for it, and it
    was verified by running the same assertion against SQLite and watching it
    fail.

    Two things fell out. `create_tables` and `lifespan_running` had no callers
    left and were deleted. And the shared engine had to move to `NullPool`: an
    HTTP test drives two event loops, and psycopg refuses a connection used from
    both — which `StaticPool` over in-memory SQLite had been absorbing.

12. ~~Give memory a way in.~~ **Done.** Memory was the most carefully
    specified subsystem here and the only one with no producer: `remember` and
    `forget` had no caller outside the tests, so `state.memory` was empty on
    every real turn and the system prompt was always absent. The read path ran
    on every turn and had never once found anything.

    The owner writes it, over HTTP (`GET`/`PUT`/`DELETE` on a session's memory),
    reusing `chat/access.py` unchanged. The model deliberately cannot — memory
    is injected into the system prompt of every later turn, so a model able to
    write it could write its own future instructions, and one injected user
    message would outlive the message that carried it. That is recorded as
    bacteria's ADR 0016 rather than left as an absence, because the intuition
    runs the other way and `remember` looks like a harmless first tool.

    Bounded in the same change, since opening the entrance without a bound
    ships the latent bug: `_format_memory` rendered every entry, so memory was
    the one channel into the context window that nothing watched. Also fixed a
    zero-inversion in both bounds — `list[-0:]` is the whole list, so asking for
    the strictest bound returned everything.

    Still session-scoped. A new conversation starts with no memory, and making
    it follow a user would change `SessionRepository`.

13. ~~Serialize commits to one session.~~ **Done**, and it was a live bug
    rather than a precaution. `commit` derived the next `seq` from the current
    maximum without a lock, so overlapping requests claimed the same position:
    five concurrent commits all took 0, and two-item commits interleaved into
    `['x-a', 'y-a', 'z-a', 'x-b', 'y-b', 'z-b']` — a turn's question and its
    answer pulled apart by other turns. The transcript is what every other
    guarantee treats as authoritative, and its ordering column was meaningless
    whenever requests overlapped.

    Fixed with a row lock on the session for the duration of the write, plus a
    unique constraint on `(session_id, seq)` so a regression fails loudly. The
    lock is per session, so two conversations never wait on each other.

    The migration repairs before it constrains. Autogenerate emitted only
    `create_unique_constraint`, which fails outright on any database that has
    served overlapping traffic — every database this bug could have reached.
    Existing duplicates are renumbered by `(seq, id)`, touching only sessions
    that actually collide, and this was checked against a database deliberately
    seeded with bad rows rather than only against an empty one.

14. ~~Let the agent suggest its own memories.~~ **Done**, as ADR 0017:
    proposing a memory and activating one are different acts, and only the
    second is a human's. The model gets a `remember` tool that can *only*
    propose; proposals live in their own table, reach no model, and become
    memory when the owner accepts one.

    That split is what makes the tool registrable at all. Memory is injected
    into the system prompt of every later turn, so a model able to write it
    directly could write its own future instructions — an injected message
    would become an instruction outliving the message that carried it. Stopping
    it at a queue a human reads is what removes that, and it also removes the
    approval blocker: a tool whose only effect is "record a suggestion" needs no
    gate, because the human is downstream rather than upstream.

    Proposals are keyed by `(source, key)` so two proposers — the tool and, in
    future, a background extractor — can both suggest `tone` without either
    silently overwriting the other. Collapsing onto one key happens at
    activation, where a person can judge it. Same rule the ingestion pipeline
    applies to duplicate records, and for the same reason.

    The ADR was amended before acceptance: it first proposed a `status` field,
    which cannot work because active memory and proposals have different keys.
    Two tables, each with a primary key stating its own rule, replaced it.

15. **Next.** Audio. This is the one that re-opens the model protocol for
   `send_stream`, which is a boundary change in bacteria and gets its own ADR
   before any code.
