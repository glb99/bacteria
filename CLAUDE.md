# fastpaip — working in this repository

## What this is

A uv workspace of two packages. `packages/bacteria` is an AI agent built as
layered infrastructure; `packages/fastpaip` is the HTTP service that hosts it.
The application depends on the agent; the agent knows nothing about the
application.

**Working inside `packages/bacteria`? Read its own
[`CLAUDE.md`](packages/bacteria/CLAUDE.md) first.** It has stricter rules than
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
just migrate
just test           # both suites
just serve          # migrates first
just worker         # deferred jobs only run if this is running
```

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
`fastpaip.core.platform.run`, and `fastpaip-serve` drives `Server.serve()`
rather than calling `uvicorn.run()`.

**Importing a module must not read settings.** `get_settings` is cached for the
process, so anything that reads it at import freezes configuration before tests
can patch it. This already happened once: procrastinate discovers tasks by
import, building the app read settings, and the chat tests called the live
Anthropic API instead of the fake. If a test monkeypatches `FASTPAIP_*`, it may
also need `get_settings.cache_clear()`.

**`just makemigration` produces a draft, not a migration.** Autogenerate wrote
`ADD COLUMN ... NOT NULL` with no default, which fails outright on a table that
already has rows. Read every generated migration and apply it to a database
that has data in it.

**Alembic must keep ignoring `procrastinate_*` tables.** They come from
procrastinate's own SQL via a migration, not from SQLModel metadata, so
autogenerate would write a migration to drop them. The filter is
`fastpaip.core.db.include_name`, used by both `migrations/env.py` and the drift
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
- **The application never imports `bacteria.interfaces`.** Two composition
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
key through the CLI, make the request. Scripts for this belong in a scratchpad,
not the repository.

**Prove a new guard can fail.** The migration drift test was checked by adding
a field without a migration and watching it break. A guard nobody has seen fail
is a guard nobody has tested.

## Testing

44 of 91 application tests still run against in-memory SQLite; only migrations
and settings use Postgres. That gap is known and recorded — repository SQL is
exercised against a database we do not deploy on. Prefer adding tests that can
run on either.

Test docstrings state the invariant *and the consequence of breaking it*. A test
whose name and body say the same thing twice is missing the point.

## Style

Comments explain *why*, never *what*. Where a plausible simpler approach was
tried and failed, say so — otherwise it gets tried again. Several docstrings
here record exactly that; keep them accurate rather than tidy.

Discuss before implementing when a change touches a boundary above, adds a
dependency, or commits to infrastructure. Small internal changes do not need
that ceremony.

## Two copies of the agent

`packages/bacteria` came in via `git subtree` and is the working copy.
A separate `~/Projects/bacteria` repository exists and is **behind** — it lacks
`session/protocol.py`, ADR 0015, and the current README. Decide which is
canonical before editing the other; right now this one is.
