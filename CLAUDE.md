# bacteria — working in this repository

A uv workspace of two packages. `backend/agent` is an AI agent built as layered
infrastructure; `backend/app` is the HTTP service that hosts it. The application
depends on the agent; the agent knows nothing about the application.

**Working inside `backend/agent`? Read its own
[`CLAUDE.md`](backend/agent/CLAUDE.md) first.** Stricter rules, two
grep-discoverable markers, and a testing bar that deliberately rejects coverage.
Do not apply this file's conventions there.

**[`docs/README.md`](docs/README.md) routes every other question.** This file
holds only what you must know before touching anything.

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
```

`just --list` is the full set. A recipe's description is the **last** contiguous
comment line above it, so put the one-line summary immediately above the recipe
and any reasoning above a blank line.

**Docker Desktop must be started by hand on this machine**, or Postgres is not
there and the suite's behaviour depends on which recipe asked —
[why that matters](docs/guides/traps.md#just-check-all-can-pass-having-run-no-database-test).

## Rules

Each line is a rule. Each link is the incident that produced it — read it before
arguing with the rule, not after. Full set: [`docs/guides/traps.md`](docs/guides/traps.md).

- **Do not strip `+psycopg` from the database URL** to "make it synchronous."
  [→](docs/guides/traps.md#do-not-strip-psycopg-from-the-database-url-to-make-it-synchronous)
- **Do not use `asyncio.set_event_loop_policy`** to fix Windows loop problems.
  [→](docs/guides/traps.md#do-not-use-asyncioset_event_loop_policy-to-fix-windows-loop-problems)
- **Do not use `asyncio.create_subprocess_*` anywhere in the application.** Use
  `await asyncio.to_thread(subprocess.run, ...)`.
  [→](docs/guides/traps.md#do-not-use-asynciocreate_subprocess_-anywhere-in-the-application)
- **Importing a module must not read settings.** `get_settings` is cached for
  the process.
  [→](docs/guides/traps.md#importing-a-module-must-not-read-settings)
- **`just makemigration` produces a draft, not a migration.** Read it, and apply
  it to a database that has rows.
  [→](docs/guides/traps.md#just-makemigration-produces-a-draft-not-a-migration)
- **Alembic must keep ignoring `procrastinate_*` tables.**
  [→](docs/guides/traps.md#alembic-must-keep-ignoring-procrastinate_-tables)
- **Branch every pull request off `main`**, never off another branch. Verify
  with `git merge-base --is-ancestor <sha> origin/main` — a "Merged" badge is
  not verification.
  [→](docs/guides/traps.md#branch-every-pull-request-off-main-never-off-another-branch)
- **`pkill` matches nothing in this shell and stays quiet about it.** Kill by
  port and check the port is free before believing a restart.
  [→](docs/guides/traps.md#pkill-matches-nothing-in-this-shell-and-says-so-by-staying-quiet)
- **Write a test command to a file and run the file.** Quoting is not portable
  across the platform shell.
  [→](docs/guides/traps.md#a-test-command-runs-through-the-platform-shell-so-quoting-is-not-portable)

## Boundaries not to erode

- **Authentication ≠ authorization.** `auth/` answers *who is calling*. Whether
  they may have a resource is decided next to that resource (`personal/access.py`).
  [ADR 0004](docs/adr/0004-authentication-is-shared-authorization-lives-next-to-the-resource.md)
- **Entrypoints hold configuration, never logic.** They are omitted from
  coverage on that basis, so logic there is untested by rule.
- **Migrations own the schema.** Nothing creates tables at startup. A test
  asserts migrations and models agree.
- **The application never imports `bacteria.agent.interfaces`.** Two composition
  roots is correct; they compose different processes.
- **Jobs are enqueued inside the caller's transaction.** That is the entire
  reason the queue is Postgres rather than Redis. Do not add a broker without
  re-reading `core/jobs.py`.
- **Features own their tables, tasks, and routes.** `core/` holds nothing that
  names a domain concept.

## Verification

**Passing tests are not evidence that something works.** A mocked Gemini test
passed while every live tool call failed; the async refactor was green while the
loop was still blocked. Exercise the real path — `just smoke` does, and CI runs
it. **Prove a new guard can fail.**

Details, including the two narrower smoke modes and what smoke deliberately does
not cover: [`docs/guides/verification.md`](docs/guides/verification.md).

**A one-off verification script belongs in a scratchpad, not in this repo.** The
distinction is whether it is a gate.

## Writing

Comments and docstrings explain *why*, never *what*, and record the plausible
approach that was tried and failed. Detail lives in the docstring, not in a doc
that drifts from it. Shape, sections, and where each kind of knowledge goes:
[`docs/guides/documentation.md`](docs/guides/documentation.md).

## Working style

Discuss before implementing when a change touches a boundary above, adds a
dependency, or commits to infrastructure. Small internal changes do not need
that ceremony.

## Naming

Two different things are called bacteria. **This one** is the workspace at
`~/Documents/Projects/bacteria`. **The origin** is `~/Documents/Projects/bacteria-core`,
frozen, and code never flows from it —
[`docs/guides/the-origin-repository.md`](docs/guides/the-origin-repository.md).
Say which one you mean.
