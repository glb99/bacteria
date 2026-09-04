# Conventions

Why the code is shaped the way it is. Each of these is visible in
[`../architecture/README.md`](../architecture/README.md) as structure rather
than as a claim.

**Authentication and authorization are separate, and stay separate.** `auth/`
answers *who is calling* and nothing else. Whether that caller may have a
particular resource is decided next to the resource — `personal/access.py` — because
only the owning feature knows what owning one means. Collapsing them is how a
service ends up treating "you know the id" as "you may read it".

**The schema belongs to Alembic.** Nothing creates tables at startup — not the
server, not the admin CLI. A process that builds its own schema starts happily
against a database missing a column and fails later at the query, which is worse
than refusing to start. A test replays every migration and asserts no diff
against the models, so a model changed without a migration fails where it is
cheap to fix.

**Entrypoints hold configuration and nothing else.** They are omitted from
coverage for that reason. If an entrypoint ever looks like it deserves a test,
that is the signal it holds logic belonging to a feature.

**The application never imports `bacteria.agent.interfaces`.** That package is the
agent's own composition root, for running it standalone. The application
composes what it needs in `entrypoints/`. Two composition roots is correct —
they compose different processes — and this rule is what stops them becoming one
tangle.

**The agent is excluded from coverage.** Its suite is architectural fitness
functions rather than line coverage, and the unevenness is deliberate — see
[ADR 0013](../../backend/agent/docs/adr/0013-test-load-bearing-invariants-only.md).
Measuring it produces a number whose only use is tempting someone to write the
tests that record exists to decline.

**I/O is awaited; computation is not.** In the agent, `async def` means "this
reaches outside the process". In the application the same rule holds down to the
database driver — one driver, `psycopg` 3, serving both SQLAlchemy and the job
queue.

**Background work goes through Postgres, not a broker.** A job is enqueued
inside the transaction that justifies it, so work cannot be silently lost in the
window between committing a row and reaching a queue. That gap is the one this
codebase is otherwise organized against, and it is why the queue is not Redis.
See `core/jobs.py`.

**Entrypoints choose the event loop.** On Windows psycopg cannot run on the
default `ProactorEventLoop`, and uvicorn hardcodes it — so `bacteria-serve`
drives the server itself rather than calling `uvicorn.run()`. All of that is in
`core/platform.py`; nothing else needs to know.

