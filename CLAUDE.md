# bacteria — working in this repository

## What this is

A uv workspace of two packages. `backend/agent` is an AI agent built as
layered infrastructure; `backend/app` is the HTTP service that hosts it.
The application depends on the agent; the agent knows nothing about the
application.

**Working inside `backend/agent`? Read its own
[`CLAUDE.md`](backend/agent/CLAUDE.md) first.** It has stricter rules than
this file — ADRs for boundary changes, two grep-discoverable markers, and a
testing bar that deliberately rejects coverage. Do not apply this file's
conventions there.

Read first, in order:

1. [`README.md`](README.md) — what it does, the API, the deliberate gaps.
2. [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — sequence diagrams. A chat
   turn touches nearly every layer.
3. [`docs/MIGRATION.md`](docs/MIGRATION.md) — how it got here and what is next.

## Commands

```bash
just db-up          # Postgres in Docker. Required before almost anything.
just install
just hooks          # pre-commit hook; once per clone
just migrate
just test           # both suites
just check-all      # what CI runs, recipe for recipe
just smoke          # real server + real worker + real requests
just serve          # migrates first
just worker         # deferred jobs only run if this is running
just stack          # all three processes in containers
```

`just --list` is the full set. A recipe's description is the **last** contiguous
comment line above it, so the one-line summary goes immediately above the recipe
and the reasoning above a blank line — otherwise `just --list` prints the tail of
an explanation, which it did for six recipes.

**Postgres must be running.** Without it, migration tests skip (loudly) and
`just serve` fails. Docker Desktop has to be started manually on this machine.

## Traps, each of which cost real time

These are not style preferences. Each is a thing that looked right, was wrong,
and took a while to diagnose.

**Do not strip `+psycopg` from the database URL to "make it synchronous."**
`postgresql+psycopg://` is psycopg 3's dialect and serves both modes —
`create_engine` gives sync, `create_async_engine` gives async. Stripping it
routes the URL to psycopg2, which is not installed.

**Do not use `asyncio.set_event_loop_policy` to fix Windows loop problems.**
uvicorn passes its own `loop_factory`, hardcoded to `ProactorEventLoop`, which
silently wins. Everything that starts a loop goes through
`bacteria.app.core.platform.run`, and `bacteria-serve` drives `Server.serve()`
rather than calling `uvicorn.run()`.

**Importing a module must not read settings.** `get_settings` is cached for the
process, so anything that reads it at import freezes configuration before tests
can patch it. This already happened once: procrastinate discovers tasks by
import, building the app read settings, and the chat tests called the live
Anthropic API instead of the fake. If a test monkeypatches `BACTERIA_*`, it may
also need `get_settings.cache_clear()`.

**`just makemigration` produces a draft, not a migration.** Autogenerate wrote
`ADD COLUMN ... NOT NULL` with no default, which fails outright on a table that
already has rows. Read every generated migration and apply it to a database
that has data in it.

**Alembic must keep ignoring `procrastinate_*` tables.** They come from
procrastinate's own SQL via a migration, not from SQLModel metadata, so
autogenerate would write a migration to drop them. The filter is
`bacteria.app.core.db.include_name`, used by both `migrations/env.py` and the drift
test.

## Boundaries not to erode

- **Authentication ≠ authorization.** `auth/` answers *who is calling* and
  nothing else. Whether they may have a resource is decided next to that
  resource (`chat/access.py`), because only the owning feature knows what
  owning one means.
- **Entrypoints hold configuration, never logic.** They are omitted from
  coverage on that basis, so logic there is untested by rule.
- **Migrations own the schema.** Nothing creates tables at startup — not the
  server, not the admin CLI. A test asserts migrations and models agree.
- **The application never imports `bacteria.agent.interfaces`.** Two composition
  roots is correct; they compose different processes.
- **Jobs are enqueued inside the caller's transaction.** That is the entire
  reason the queue is Postgres rather than Redis. Do not add a broker without
  re-reading `core/jobs.py`.
- **Features own their tables, tasks, and routes.** `core/` holds nothing that
  names a domain concept.

## Verification

**Passing tests are not evidence that something works.** This has been true
repeatedly here, not theoretically:

- A mocked Gemini test passed while every live tool call failed.
- The async refactor was green while the loop was still being blocked; a
  heartbeat measurement showed otherwise.
- The queue's tests passed before the app could enqueue anything at all.

Exercise the real path. Start the server on a socket, run the worker, issue a
key through the CLI, make the request.

`just smoke` now does exactly that, as `scripts/smoke.py`, and is run by CI. It
issues a credential through the admin CLI, drives a real server and a real
worker over HTTP, and asserts the things a test cannot reach — most importantly
that a deferred job is picked up by a worker in another process, which no test
run can show because there is no worker in one.

**A one-off verification script still belongs in a scratchpad rather than here.**
The distinction is whether it is a gate. `scripts/smoke.py` is kept because it
runs on every pull request and fails them; a script written to answer one
question, once, is not that, and adding it to the repository leaves behind
something nobody maintains and nobody trusts.

What `just smoke` deliberately does not cover: an agent turn. That needs a model
provider, and the options are billing a vendor from CI or putting a test-only
seam into production code. The turn is still verified by hand.

**Prove a new guard can fail.** The migration drift test was checked by adding
a field without a migration and watching it break. A guard nobody has seen fail
is a guard nobody has tested.

## Testing

**Every test runs on Postgres.** `just db-up` first, or the suite skips. There is
no SQLite anywhere — not as a fallback, not as a fast path. It was removed
because it was actively lying: SQLite ignores `DateTime(timezone=True)` and
returns naive datetimes, so every timestamp in the application round-tripped one
way under test and another in production, and no test could see it.

`tests/conftest.py` owns the fixtures. One throwaway database per run, truncated
between tests. Two things in it are load-bearing and non-obvious:

- The `engine` fixture uses `NullPool`, and HTTP tests must request
  `backend_options` and pass it to `TestClient`. An HTTP test drives two event
  loops — pytest-asyncio's and the one `TestClient` opens in its own thread —
  and a psycopg connection shared across them fails with *another command is
  already in progress*.
- Loop selection is a `pytest_asyncio_loop_factories` hook, not a policy, for
  the reason `core/platform.py` gives.

Test docstrings state the invariant *and the consequence of breaking it*. A test
whose name and body say the same thing twice is missing the point.

## Style

Comments explain *why*, never *what*. Where a plausible simpler approach was
tried and failed, say so — otherwise it gets tried again. Several docstrings
here record exactly that; keep them accurate rather than tidy.

Discuss before implementing when a change touches a boundary above, adds a
dependency, or commits to infrastructure. Small internal changes do not need
that ceremony.

## The other bacteria repository

**Two different things are now called bacteria, and the ambiguity is new.** This
repository took the name in the rename that produced `bacteria.agent` and
`bacteria.app`; the repository below had it first. When either is meant, say
which:

- **this one** — the workspace, at `~/Documents/Projects/bacteria`, whose agent
  package is `backend/agent` and imports as `bacteria.agent`.
- **the origin** — `~/Projects/bacteria`, frozen, described below.

`backend/agent` came in via `git subtree` and is the working copy. Every
change to the agent belongs here. The subtree link is not maintained — the
directory has since been renamed and its modules moved under a namespace, so a
future `git subtree pull` would not apply cleanly and should not be attempted.

`~/Projects/bacteria` is where it started — the study project it was built in,
working through an article series. It is frozen at `f58e89b`, 2026-08-06, which
is **before the async refactor**: its code is synchronous throughout and has no
`session/protocol.py`. Never copy code from it in this direction.

It is not merely stale, though, and that is the part worth knowing. It holds
`docs/SYSTEM_DESIGN.md` and `docs/sequence.mmd`, which **exist nowhere else** —
the part-by-part design record that the ADRs replaced. So the two diverged in
kind and not only in commits: this copy has `docs/adr/` and no `SYSTEM_DESIGN.md`,
that one has the reverse.

Which means "sync them" is the wrong instinct in both directions. Code flows
neither way; that repository is a frozen origin. If anything in
`SYSTEM_DESIGN.md` still earns its place, move that content deliberately into an
ADR or `ARCHITECTURE.md` — do not reintroduce the article-part framing, which
was retired on purpose.
