# Traps

Each entry is a thing that looked right, was wrong, and took real time to
diagnose. `CLAUDE.md` carries the rule as a one-liner; the evidence is here.

These are not style preferences. Each is a thing that looked right, was wrong,
and took a while to diagnose.

## Do not strip `+psycopg` from the database URL to "make it synchronous."

`postgresql+psycopg://` is psycopg 3's dialect and serves both modes —
`create_engine` gives sync, `create_async_engine` gives async. Stripping it
routes the URL to psycopg2, which is not installed.

## Do not use `asyncio.set_event_loop_policy` to fix Windows loop problems.

uvicorn passes its own `loop_factory`, hardcoded to `ProactorEventLoop`, which
silently wins. Everything that starts a loop goes through
`bacteria.app.core.platform.run`, and `bacteria-serve` drives `Server.serve()`
rather than calling `uvicorn.run()`.

## Importing a module must not read settings.

`get_settings` is cached for the
process, so anything that reads it at import freezes configuration before tests
can patch it. This already happened once: procrastinate discovers tasks by
import, building the app read settings, and the chat tests called the live
Anthropic API instead of the fake. If a test monkeypatches `BACTERIA_*`, it may
also need `get_settings.cache_clear()`.

## `just makemigration` produces a draft, not a migration.

Autogenerate wrote
`ADD COLUMN ... NOT NULL` with no default, which fails outright on a table that
already has rows. Read every generated migration and apply it to a database
that has data in it.

## `pkill` matches nothing in this shell, and says so by staying quiet.

It
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

## Branch every pull request off `main`, never off another branch.

A stacked PR
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

## Do not use `asyncio.create_subprocess_*` anywhere in the application.

This
process runs on `SelectorEventLoop` on Windows *on purpose* — psycopg's async
mode refuses the Proactor loop — and the selector loop has **no subprocess
support at all**. The async spelling raises a bare `NotImplementedError` from
inside asyncio, in production as well as under test, and the traceback names
`base_events.py` rather than anything you wrote.

Run the process in a thread instead: `await asyncio.to_thread(subprocess.run,
..., timeout=...)`. It blocks a worker rather than the loop and behaves the same
on every platform. `architecture/probes.py` is the one place that does this and
says why.

## A test command runs through the platform shell, so quoting is not portable.

`"py" -c 'import sys; sys.exit(3)'` is one program under `sh` and a syntax error
under `cmd` — which exits 1, and is then reported as a failing suite. Write the
script to a file and run the file. This cost a wrong assertion that looked like
a bug in the probe.

## Alembic must keep ignoring `procrastinate_*` tables.

They come from
procrastinate's own SQL via a migration, not from SQLModel metadata, so
autogenerate would write a migration to drop them. The filter is
`bacteria.app.core.db.include_name`, used by both `migrations/env.py` and the drift
test.


## `just check-all` can pass having run no database test


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
