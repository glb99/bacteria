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
just check-all      # what CI runs, minus the recorded exceptions
just smoke          # real server + real worker + real requests
just serve          # migrates first
just worker         # deferred jobs only run if this is running
just stack          # all three processes in containers
just stack-smoke    # build the image and smoke the containers; stack-stop after
```

`just --list` is the full set. A recipe's description is the **last** contiguous
comment line above it, so the one-line summary goes immediately above the recipe
and the reasoning above a blank line — otherwise `just --list` prints the tail of
an explanation, which it did for six recipes.

**Postgres must be running.** Docker Desktop has to be started manually on this
machine. Without it `just serve` fails, and the suite's behaviour depends on
which recipe asked: `just test-app` skips the database tests, `just cov` — and
therefore `just check-all` — fails them, because `cov` sets `REQUIRE_POSTGRES`.

That split exists because the skip made `check-all` a gate that could not fail.
pytest exits 0 on a run that skipped everything, so with Docker stopped the
recipe people are told to run before pushing reported success having executed no
database test at all. Iterating on one file from an editor should still skip;
the aggregate gate has no business claiming success. Never name that variable
with the `BACTERIA_` prefix — an unrecognized one is a refusal to boot.

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

**`pkill` matches nothing in this shell, and says so by staying quiet.** It
returns without killing `bacteria-serve`, so a "restart" leaves the old process
holding port 8000, the new one exits with `[Errno 10048] error while attempting
to bind`, and every request after that is answered by a server running the *old*
configuration. That failure looks exactly like success: the endpoint responds,
the log has no traceback anyone reads, and the result is confidently wrong. It
cost two rounds of wrong conclusions in one session while testing a setting that
had not been reloaded.

Kill by port instead, and check the port is free before believing a restart:

    (Get-NetTCPConnection -LocalPort 8000 -State Listen).OwningProcess | Stop-Process -Force

Then `grep -c "bind on address"` the new log. Zero means the server you are
talking to is the one you just started.

**Branch every pull request off `main`, never off another branch.** A stacked PR
merges into its parent branch, and once that parent has itself gone into `main`
the merge lands somewhere nothing leads to: GitHub shows the PR green and merged,
and the code is not on `main`. This has happened three times here and cost a
recovery PR each time — most recently #63, whose 280-line
`chat/graph_candidates.py` was absent from `main` while its PR read as merged.

The mechanism supposed to prevent it — GitHub retargeting a child PR when its
base branch is deleted — does not fire when merges are batched: #64, #65 and #66
were merged inside 31 seconds and the last two stranded. Where work genuinely
depends on unmerged work, merge the parent first and rebase onto `main`.

Checking is one command, and a PR's "Merged" badge is not it:

    git merge-base --is-ancestor <sha> origin/main

**Do not use `asyncio.create_subprocess_*` anywhere in the application.** This
process runs on `SelectorEventLoop` on Windows *on purpose* — psycopg's async
mode refuses the Proactor loop — and the selector loop has **no subprocess
support at all**. The async spelling raises a bare `NotImplementedError` from
inside asyncio, in production as well as under test, and the traceback names
`base_events.py` rather than anything you wrote.

Run the process in a thread instead: `await asyncio.to_thread(subprocess.run,
..., timeout=...)`. It blocks a worker rather than the loop and behaves the same
on every platform. `architecture/probes.py` is the one place that does this and
says why.

**A test command runs through the platform shell, so quoting is not portable.**
`"py" -c 'import sys; sys.exit(3)'` is one program under `sh` and a syntax error
under `cmd` — which exits 1, and is then reported as a failing suite. Write the
script to a file and run the file. This cost a wrong assertion that looked like
a bug in the probe.

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
  [ADR 0004](docs/adr/0004-authentication-is-shared-authorization-lives-next-to-the-resource.md)
  records it, including the consequence: ingestion never wrote an ownership
  rule, so a batch is authenticated and unowned.
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

Two narrower modes exist alongside it, and both cover something the plain run
cannot:

- `just smoke --in-process-worker` runs the topology a deployment actually uses
  — one process, worker inside the API behind `BACTERIA_RUN_WORKER_IN_API`
  (ADR 0001). Everything else here runs the two-process shape, so that flag was
  load-bearing in production and exercised nowhere. It failed exactly that way
  once: the variable never reached the process, the service conversed normally,
  nothing drained the queue, and it was found by hand days later. Note that a
  local `.env` setting the flag makes the *plain* run a hybrid.
- `just stack-smoke` builds the Docker image and runs the same checks against
  the containers, including that the console is served from the image. The
  platform's builder never reads the Dockerfile, so that is a second packaging
  path, and it is the exit route off FastAPI Cloud.

What `just smoke` deliberately does not cover: an agent turn. That needs a model
provider, and the options are billing a vendor from CI or putting a test-only
seam into production code. The turn is still verified by hand.

**Prove a new guard can fail.** The migration drift test was checked by adding
a field without a migration and watching it break. A guard nobody has seen fail
is a guard nobody has tested.

## Testing

**Every test runs on Postgres.** `just db-up` first, or the suite skips — or
fails, under `just cov`; see the note above. There is no SQLite anywhere — not
as a fallback, not as a fast path. It was removed
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
- **the origin** — `~/Documents/Projects/bacteria-core`, frozen, described below.

This file said the origin was at `~/Projects/bacteria` until that path was
checked and found not to exist. It is `bacteria-core`, in the same directory as
everything else. A third directory, `~/Documents/Projects/bacteria-main`, shares
the prefix and is a different project entirely — not a git repository, and
nothing here depends on it.

`backend/agent` came in via `git subtree` and is the working copy. Every
change to the agent belongs here. The subtree link is not maintained — the
directory has since been renamed and its modules moved under a namespace, so a
future `git subtree pull` would not apply cleanly and should not be attempted.

`bacteria-core` is where it started — the study project it was built in,
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
